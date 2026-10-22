"""libclang 만으로 호출 순서(시나리오)와 클래스 관계를 뽑는다. clang-uml 이 없을 때의 대체 경로.

clang-uml 보다 얻는 것이 적다(템플릿 관계, 조건 분기 블록, include 그래프 없음).
대신 pip 의존성만으로 동작하므로 PoC 와 CI 초기 구성에 쓴다.

두 단계로 동작한다.
1. 모든 TU 를 파싱해 함수 정의마다 "호출 목록" 을 모으고(USR 기준), 클래스의 상속·필드 관계를 모은다.
2. scenarios.yaml 의 진입 함수에서 깊이 제한 DFS 로 호출 순서를 만든다.
   가상 함수 호출은 정적으로 확정되지 않으므로 "virtual 후보" 로 표시하고 override 를 함께 따라간다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clang import cindex

from ..config import Config
from .comments import _CLASS_KINDS, _FUNCTION_KINDS, _METHOD_KINDS, _loc, _qualified, _under, parse_args
from .model import ClassInfo, KnowledgeModel, Location, Message, PackageInfo, Relation, Scenario, relpath

_MAX_MESSAGES = 120


@dataclass
class Call:
    callee_usr: str
    callee_name: str          # 짧은 이름 (메서드 이름)
    callee_owner: str         # 클래스 짧은 이름 또는 파일 stem
    loc: Location | None
    # direct | virtual | pointer(함수 포인터 멤버) | callable(std::function 등) | unresolved
    kind: str = "direct"


@dataclass
class FuncDef:
    usr: str
    qualified: str
    display: str              # 이름(인자 타입) 형태
    owner: str
    loc: Location | None
    calls: list[Call] = field(default_factory=list)


@dataclass
class Graph:
    defs: dict[str, FuncDef] = field(default_factory=dict)
    # 클래스 USR -> (짧은 이름, 완전한 이름)
    classes: dict[str, tuple[str, str]] = field(default_factory=dict)
    # 오버라이드: 기반 메서드 USR -> 파생 메서드 USR 목록
    overrides: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    inherits: list[tuple[str, str]] = field(default_factory=list)       # (derived, base) 완전한 이름
    fields: list[tuple[str, str, str]] = field(default_factory=list)    # (owner, target, field name)
    # 클래스 완전한 이름 -> {메서드 displayname: USR}. override 계산용.
    methods: dict[str, dict[str, str]] = field(default_factory=lambda: defaultdict(dict))


def _short(qualified: str) -> str:
    return qualified.rsplit("::", 1)[-1]


def _owner_of(cursor: cindex.Cursor, root: Path) -> str:
    parent = cursor.semantic_parent
    if parent is not None and parent.kind in _CLASS_KINDS:
        return _short(_qualified(parent))
    f = cursor.location.file
    return Path(f.name).stem if f else "?"


def _type_decl(t: cindex.Type, root: Path, depth: int = 0) -> cindex.Cursor | None:
    """std::unique_ptr<Foo>, std::vector<std::unique_ptr<Foo>>, Foo*, const Foo& 에서
    소스 루트 안에 선언된 Foo 를 찾는다. 루트 밖 템플릿(std::)은 인자를 차례로 들여다본다."""
    if depth > 4:
        return None
    t = t.get_canonical()
    for _ in range(4):
        if t.kind in (cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE, cindex.TypeKind.RVALUEREFERENCE):
            t = t.get_pointee()
            continue
        break
    decl = t.get_declaration()
    if decl is not None and decl.kind in _CLASS_KINDS and decl.spelling and _under(decl, root):
        return decl
    n = t.get_num_template_arguments()
    for i in range(max(n, 0)):
        found = _type_decl(t.get_template_argument_type(i), root, depth + 1)
        if found is not None:
            return found
    return None


def _is_qualified_call(node: cindex.Cursor) -> bool:
    """`Base::method(...)` 처럼 한정된 호출은 가상 함수라도 정적으로 결정된다."""
    for tok in node.get_tokens():
        if tok.spelling == "(":
            return False
        if tok.spelling == "::":
            return True
    return False


def _callee_expr_name(node: cindex.Cursor) -> str:
    for c in node.get_children():
        if c.kind in (cindex.CursorKind.MEMBER_REF_EXPR, cindex.CursorKind.DECL_REF_EXPR) and c.spelling:
            return c.spelling
        inner = _callee_expr_name(c)
        if inner:
            return inner
    return ""


def _walk_all(cursor: cindex.Cursor, root: Path):
    for child in cursor.get_children():
        if not _under(child, root):
            continue
        yield child
        yield from _walk_all(child, root)


def _classify_call(node: cindex.Cursor, ref: cindex.Cursor | None, loc: Location | None,
                   fd_owner: str, root: Path) -> Call | None:
    """이 호출 표현식이 어떤 종류의 호출인지 판정한다. 문서에 올릴 것이 없으면 None 을 돌려준다."""
    if ref is None:
        return Call("", _callee_expr_name(node) or "(알 수 없는 호출)", "?", loc, kind="unresolved")
    if ref.kind in (cindex.CursorKind.FIELD_DECL, cindex.CursorKind.VAR_DECL, cindex.CursorKind.PARM_DECL):
        # 함수 포인터 멤버 호출: callbacks_->process_capture_result(...)
        return Call("", ref.spelling, _owner_of(ref, root), loc, kind="pointer")
    if ref.kind == cindex.CursorKind.CXX_METHOD and ref.spelling == "operator()" and not _under(ref, root):
        # std::function 같은 호출 가능 객체: handler_(*frame)
        return Call("", _callee_expr_name(node) or "callable", fd_owner, loc, kind="callable")
    if ref.kind not in (_METHOD_KINDS | _FUNCTION_KINDS) or not _under(ref, root):
        return None
    if (ref.kind == cindex.CursorKind.CONSTRUCTOR and ref.semantic_parent is not None
            and not ref.semantic_parent.spelling):
        return None
    is_virtual = (ref.kind == cindex.CursorKind.CXX_METHOD and ref.is_virtual_method()
                  and not _is_qualified_call(node))
    return Call(ref.get_usr(), ref.spelling, _owner_of(ref, root), loc,
                kind="virtual" if is_virtual else "direct")


def _deferred_targets(node: cindex.Cursor, root: Path, callee_usr: str) -> list[cindex.Cursor]:
    """호출 인자로 넘어간 메서드·함수 선언을 모은다.

    `invokeMethod(&PipelineHandler::queueRequest, ...)` 나 `connect(&Class::slot)` 처럼 메서드를
    값으로 넘기면, 그 메서드는 이 호출 자리에서 실행되지 않는다. 실행 시점과 스레드는 큐나 신호
    구현이 정하므로 정적 추적으로는 순서를 알 수 없다. 대상 이름은 알 수 있으므로 경계로 기록한다.
    중첩된 호출 표현식은 바깥 순회가 따로 보기 때문에 여기서는 들어가지 않는다.
    """
    found: list[cindex.Cursor] = []
    seen: set[str] = set()

    def walk(n: cindex.Cursor) -> None:
        for child in n.get_children():
            if child.kind == cindex.CursorKind.CALL_EXPR:
                continue
            if child.kind == cindex.CursorKind.DECL_REF_EXPR:
                target = child.referenced
                if (target is not None and target.kind in (_METHOD_KINDS | _FUNCTION_KINDS)
                        and _under(target, root)):
                    usr = target.get_usr()
                    if usr and usr != callee_usr and usr not in seen:
                        seen.add(usr)
                        found.append(target)
            walk(child)

    walk(node)
    return found


def build_graph(cfg: Config, entries: list[dict[str, Any]]) -> Graph:
    index = cindex.Index.create()
    root = cfg.source_root.resolve()
    g = Graph()
    for entry in entries:
        src, args = parse_args(entry)
        try:
            tu = index.parse(str(src), args=args)
        except cindex.TranslationUnitLoadError:
            continue
        for cur in _walk_all(tu.cursor, root):
            if cur.kind in _CLASS_KINDS and cur.is_definition() and cur.spelling:
                q = _qualified(cur)
                g.classes[cur.get_usr()] = (cur.spelling, q)
                for child in cur.get_children():
                    if child.kind == cindex.CursorKind.CXX_METHOD:
                        g.methods[q][child.displayname] = child.get_usr()
                    if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                        base = child.referenced
                        if base is not None and _under(base, root) and (q, _qualified(base)) not in g.inherits:
                            g.inherits.append((q, _qualified(base)))
                    elif child.kind == cindex.CursorKind.FIELD_DECL:
                        decl = _type_decl(child.type, root)
                        if decl is not None and _qualified(decl) != q:
                            edge = (q, _qualified(decl), child.spelling)
                            if edge not in g.fields:
                                g.fields.append(edge)
                continue

            if cur.kind not in (_METHOD_KINDS | _FUNCTION_KINDS) or not cur.is_definition():
                continue
            usr = cur.get_usr()
            fd = FuncDef(usr=usr, qualified=_qualified(cur), display=cur.displayname,
                         owner=_owner_of(cur, root), loc=_loc(cur, root))
            for node in _walk_all(cur, root):
                if node.kind != cindex.CursorKind.CALL_EXPR:
                    continue
                loc = (Location(file=relpath(node.location.file.name, root), line=node.location.line)
                       if node.location.file else None)
                ref = node.referenced
                call = _classify_call(node, ref, loc, fd.owner, root)
                if call is not None:
                    fd.calls.append(call)
                # 인자로 넘어간 메서드는 이 자리에서 실행되지 않는다. 신호·큐 경계를 남긴다.
                callee_usr = ref.get_usr() if ref is not None else ""
                for target in _deferred_targets(node, root, callee_usr):
                    fd.calls.append(Call(target.get_usr(), target.spelling, _owner_of(target, root),
                                         loc, kind="deferred"))
            g.defs.setdefault(usr, fd)

    # override: 파생 클래스에 같은 displayname 의 메서드가 있으면 기반 메서드의 후보로 등록한다.
    # (이 libclang 바인딩에는 get_overridden_cursors 가 없어서 이름으로 맞춘다. 상속 사슬을 따라 올라간다.)
    bases_of: dict[str, list[str]] = defaultdict(list)
    for derived, base in g.inherits:
        bases_of[derived].append(base)
    for derived, methods in g.methods.items():
        stack = list(bases_of.get(derived, []))
        seen: set[str] = set()
        while stack:
            base = stack.pop()
            if base in seen:
                continue
            seen.add(base)
            for display, usr in methods.items():
                base_usr = g.methods.get(base, {}).get(display)
                if base_usr and base_usr != usr and usr not in g.overrides[base_usr]:
                    g.overrides[base_usr].append(usr)
            stack.extend(bases_of.get(base, []))
    return g


def _normalize_params(params: str) -> str:
    # HAL3 C 헤더는 `const struct camera3_device *` 처럼 struct 를 붙여 쓰는 곳과 typedef 를 쓰는 곳이 섞인다.
    params = re.sub(r"\b(struct|class|enum|union)\s+", "", params.rstrip(")"))
    return re.sub(r"\s+", "", params)


def _normalize_sig(sig: str) -> tuple[str, str | None]:
    """(이름, 인자) 를 돌려준다. 괄호가 없으면 인자는 None 이고, `f()` 의 인자는 빈 문자열이다."""
    name, paren, params = sig.partition("(")
    return name.strip(), (_normalize_params(params) if paren else None)


def match_entry(g: Graph, from_sig: str) -> tuple[FuncDef | None, str]:
    """진입 함수와, 찾지 못했거나 고르지 못한 이유를 돌려준다.

    같은 이름이 여럿인데 시그니처로 하나를 고를 수 없으면 임의의 정의를 고르지 않는다.
    엉뚱한 함수에서 시작한 시나리오가 문서에 조용히 실리기 때문이다.
    """
    name, params = _normalize_sig(from_sig)
    candidates = [fd for fd in g.defs.values() if fd.qualified == name or fd.qualified.endswith("::" + name)]
    if not candidates:
        return None, "같은 이름의 함수 정의가 없습니다"
    listed = ", ".join(sorted(f"{fd.qualified.rpartition('::')[0] or '<전역>'}::{fd.display}" for fd in candidates))
    if params is not None:
        exact = [fd for fd in candidates if _normalize_params(fd.display.partition("(")[2]) == params]
        if len(exact) == 1:
            return exact[0], ""
        if len(exact) > 1:
            return None, f"시그니처가 같은 정의가 {len(exact)}개입니다. 클래스나 네임스페이스를 붙이세요: {listed}"
    if len(candidates) == 1:
        if params is not None:
            print(f"[callgraph] 경고: 인자가 다르지만 같은 이름의 정의가 하나뿐이라 사용합니다: "
                  f"{from_sig} -> {listed}")
        return candidates[0], ""
    return None, f"같은 이름의 정의가 {len(candidates)}개라 고를 수 없습니다: {listed}"


def find_entry(g: Graph, from_sig: str) -> FuncDef | None:
    return match_entry(g, from_sig)[0]


def trace(g: Graph, entry: FuncDef, depth: int) -> tuple[list[Message], int, int]:
    messages: list[Message] = []
    unresolved = 0
    deferred = 0

    def visit(fd: FuncDef, level: int, path: set[str]) -> None:
        nonlocal unresolved, deferred
        if level >= depth or len(messages) >= _MAX_MESSAGES:
            return
        for call in fd.calls:
            if call.kind == "deferred":
                # 대상은 알지만 이 자리에서 실행되지 않는다. 따라 들어가면 없는 순서를 만들게 된다.
                deferred += 1
                target = g.defs.get(call.callee_usr)
                messages.append(Message(src=fd.owner, dst=(target.owner if target else call.callee_owner),
                                        name=call.callee_name, loc=call.loc,
                                        note="예약된 호출, 실행 순서는 정적으로 확인 불가"))
                continue
            if call.kind in ("pointer", "callable", "unresolved"):
                unresolved += 1
                label = {"pointer": "함수 포인터, 정적 추적 불가", "callable": "콜백 객체, 정적 추적 불가",
                         "unresolved": "정적 추적 불가"}[call.kind]
                messages.append(Message(src=fd.owner, dst=call.callee_owner, name=call.callee_name,
                                        loc=call.loc, note=label))
                continue
            targets = [call.callee_usr]
            note = ""
            if call.kind == "virtual":
                over = g.overrides.get(call.callee_usr, [])
                # 기반 구현이 있으면(순수 가상이 아니면) 그것도 후보다.
                base_def = g.defs.get(call.callee_usr)
                targets = ([call.callee_usr] if base_def else []) + over
                if len(targets) > 1:
                    note = "virtual 후보"
                elif targets:
                    note = "virtual, 현재 구현 하나"   # 지금은 하나지만 동적 디스패치라는 사실은 남긴다.
                else:
                    unresolved += 1
                    messages.append(Message(src=fd.owner, dst=call.callee_owner, name=call.callee_name,
                                            loc=call.loc, note="virtual, override 없음"))
                    continue
            for t_usr in targets:
                t = g.defs.get(t_usr)
                owner = t.owner if t else call.callee_owner
                messages.append(Message(src=fd.owner, dst=owner, name=call.callee_name, loc=call.loc, note=note))
                if t and t_usr not in path:
                    visit(t, level + 1, path | {t_usr})

    visit(entry, 0, {entry.usr})
    return messages, unresolved, deferred


def mermaid_sequence(entry: FuncDef, messages: list[Message]) -> str:
    parts = ["sequenceDiagram"]
    seen: list[str] = []
    for name in [entry.owner] + [m.dst for m in messages]:
        if name not in seen:
            seen.append(name)
            parts.append(f"    participant {name}")
    for m in messages:
        arrow = "-->>" if m.note else "->>"
        label = f"{m.name}()" + (f" [{m.note}]" if m.note else "")
        parts.append(f"    {m.src}{arrow}{m.dst}: {label}")
    return "\n".join(parts)


def mermaid_class(model: KnowledgeModel) -> str:
    parts = ["classDiagram"]
    for c in sorted(model.classes.values(), key=lambda x: x.name):
        parts.append(f"    class {_short(c.name)} {{")
        for m in c.methods[:6]:
            parts.append(f"        +{m.name}()")
        parts.append("    }")
    for r in model.relations:
        s, t = _short(r.source), _short(r.target)
        if r.type == "inheritance":
            parts.append(f"    {t} <|-- {s}")
        elif r.type == "association":
            parts.append(f"    {s} --> {t}")
    return "\n".join(parts)


def package_of(file: str, depth: int) -> str:
    """패키지 = 선언 파일 경로의 앞 depth 개 디렉터리.

    clang-uml 의 package_type: directory 와 같은 규칙이되, 깊이를 설정으로 정한다.
    경로가 depth 보다 얕으면 그 파일이 들어 있는 디렉터리까지만 쓰고, 루트 바로 아래 파일은
    "(root)" 로 묶는다. 깊이를 올려도 얕은 트리가 빈 이름을 만들지 않게 하려는 처리다.
    """
    parts = Path(file).parts
    if len(parts) > depth:
        return "/".join(parts[:depth])
    return "/".join(parts[:-1]) or "(root)"


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]]) -> dict[str, int]:
    g = build_graph(cfg, entries)
    root = cfg.source_root.resolve()

    depth = max(1, cfg.package_depth)
    for c in model.classes.values():
        if c.loc and not c.package:
            c.package = package_of(c.loc.file, depth)
        if c.package:
            p = model.packages.setdefault(c.package, PackageInfo(name=c.package, path=c.package))
            if c.name not in p.classes:
                p.classes.append(c.name)

    for derived, base in g.inherits:
        model.relations.append(Relation(source=derived, target=base, type="inheritance"))
        c = model.classes.get(derived)
        if c is not None and base not in c.bases:
            c.bases.append(base)
    seen_assoc: set[tuple[str, str]] = set()
    for owner, target, _name in g.fields:
        if (owner, target) not in seen_assoc:
            seen_assoc.add((owner, target))
            model.relations.append(Relation(source=owner, target=target, type="association"))

    stats = {"functions": len(g.defs), "scenarios": 0, "missing_entries": 0}
    for sc in cfg.scenarios():
        entry, reason = match_entry(g, sc["from"])
        if entry is None:
            print(f"[callgraph] 시나리오 {sc['id']}: 진입 함수를 정하지 못했습니다: {sc['from']} ({reason})")
            stats["missing_entries"] += 1
            continue
        messages, unresolved, deferred = trace(g, entry, int(sc.get("depth", 4) or 4))
        model.scenarios[sc["id"]] = Scenario(
            id=sc["id"], title=sc.get("title", sc["id"]), entry=sc["from"],
            participants=list(dict.fromkeys([entry.owner] + [m.dst for m in messages])),
            messages=messages, mermaid=mermaid_sequence(entry, messages),
            unresolved=unresolved, deferred=deferred)
        stats["scenarios"] += 1

    diagrams = cfg.diagrams_dir
    diagrams.mkdir(parents=True, exist_ok=True)
    (diagrams / "class_overview.mmd").write_text(mermaid_class(model) + "\n", encoding="utf-8")
    for sid, sc in model.scenarios.items():
        (diagrams / f"seq_{sid}.mmd").write_text(sc.mermaid + "\n", encoding="utf-8")
    model.meta["callgraph"] = stats
    return stats
