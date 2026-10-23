"""libclang 으로 선언/정의 위치와 주석을 뽑는다. Doxygen 대체.

compile DB 의 플래그를 그대로 써서 NDK 구성 기준으로 파싱한다.
-fparse-all-comments 를 붙여서 Doxygen 형식이 아닌 일반 `//` 주석도 선언에 붙인 주석으로 읽는다.
pip 의 `libclang` 패키지가 공유 라이브러리를 함께 설치하므로 시스템 LLVM 이 없어도 된다.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Iterator

from clang import cindex

from .. import compdb
from ..config import Config
from .model import ClassInfo, FunctionInfo, KnowledgeModel, Location, Method, relpath

_CLASS_KINDS = {
    cindex.CursorKind.CLASS_DECL: "class",
    cindex.CursorKind.STRUCT_DECL: "struct",
    cindex.CursorKind.CLASS_TEMPLATE: "class",
    cindex.CursorKind.ENUM_DECL: "enum",
}
_METHOD_KINDS = {cindex.CursorKind.CXX_METHOD, cindex.CursorKind.CONSTRUCTOR, cindex.CursorKind.DESTRUCTOR,
                 cindex.CursorKind.FUNCTION_TEMPLATE}
_FUNCTION_KINDS = {cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.FUNCTION_TEMPLATE}
_CONTAINER_KINDS = {cindex.CursorKind.NAMESPACE, cindex.CursorKind.TRANSLATION_UNIT, cindex.CursorKind.LINKAGE_SPEC,
                    cindex.CursorKind.UNEXPOSED_DECL} | set(_CLASS_KINDS)

# 컴파일 전용 플래그. 파싱에는 필요 없고 libclang 이 거부할 수 있어 제거한다.
_DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "-Xclang", "-fdebug-compilation-dir"}
_DROP_ALONE = {"-c", "-MD", "-MMD", "-MP", "-fPIC", "-fPIE", "-pipe", "-g", "-gdwarf-4", "-gdwarf-5"}
_DROP_PREFIX = ("-O", "-Wa,", "-Wl,", "-fstack-protector", "-fuse-ld", "-flto", "-fprofile", "-fcoverage")

_COMMENT_JUNK = re.compile(r"^\s*(/\*+|\*+/|\*|//+|///<|//!|/\*\*|@brief|\\brief)\s?")


def parse_args(entry: dict[str, Any]) -> tuple[Path, list[str]]:
    """compile DB 항목에서 (소스 파일, libclang 에 넘길 인자) 를 만든다."""
    argv = compdb._argv(entry)
    src = Path(str(entry.get("file", "")))
    if not src.is_absolute():
        src = Path(str(entry.get("directory", "."))) / src
    out: list[str] = []
    skip_next = False
    for tok in argv[1:]:                      # argv[0] 은 컴파일러
        if skip_next:
            skip_next = False
            continue
        if tok in _DROP_WITH_VALUE:
            skip_next = True
            continue
        if tok in _DROP_ALONE or tok.startswith(_DROP_PREFIX):
            continue
        if Path(tok).name == src.name and tok.endswith(src.suffix):
            continue                          # 소스 파일 자체
        out.append(tok)
    out.append("-fparse-all-comments")
    return src, out


def _brief(cursor: cindex.Cursor) -> str:
    text = cursor.brief_comment or ""
    if not text and cursor.raw_comment:
        for line in cursor.raw_comment.splitlines():
            cleaned = _COMMENT_JUNK.sub("", line).strip()
            if cleaned:
                text = cleaned
                break
    return " ".join(text.split())[:200]


def _qualified(cursor: cindex.Cursor) -> str:
    parts: list[str] = []
    cur = cursor
    while cur is not None and cur.kind != cindex.CursorKind.TRANSLATION_UNIT:
        if cur.kind in (cindex.CursorKind.NAMESPACE, *_CLASS_KINDS) or cur == cursor:
            if cur.spelling:
                parts.append(cur.spelling)
        cur = cur.semantic_parent
    return "::".join(reversed(parts))


def _loc(cursor: cindex.Cursor, root: Path) -> Location | None:
    f = cursor.location.file
    if f is None:
        return None
    return Location(file=relpath(f.name, root), line=int(cursor.location.line))


# 소스 루트 기준 제외 glob (cfg.source.exclude). extract.run 이 set_excludes 로 넣는다.
_EXCLUDES: list[re.Pattern[str]] = []
_UNDER_CACHE: dict[str, bool] = {}


def is_excluded(rel: str) -> bool:
    """소스 루트 기준 상대 경로가 cfg.source.exclude 에 걸리는가."""
    return any(p.fullmatch(rel) for p in _EXCLUDES)


def set_excludes(patterns: list[str]) -> None:
    from ..matching import glob_to_regex

    _EXCLUDES[:] = [glob_to_regex(p) for p in patterns]
    _UNDER_CACHE.clear()


def _under(cursor: cindex.Cursor, root: Path) -> bool:
    """소스 루트 안이면서 exclude 에 걸리지 않는 파일의 커서인가."""
    f = cursor.location.file
    if f is None:
        return False
    cached = _UNDER_CACHE.get(f.name)
    if cached is not None:
        return cached
    try:
        rel = Path(f.name).resolve().relative_to(root).as_posix()
        ok = not any(p.fullmatch(rel) for p in _EXCLUDES)
    except ValueError:
        ok = False
    _UNDER_CACHE[f.name] = ok
    return ok


def _walk(cursor: cindex.Cursor, root: Path) -> Iterator[cindex.Cursor]:
    """소스 루트 밖(NDK sysroot, libc++)은 내려가지 않는다."""
    for child in cursor.get_children():
        if child.kind != cindex.CursorKind.TRANSLATION_UNIT and not _under(child, root):
            continue
        yield child
        if child.kind in _CONTAINER_KINDS:
            yield from _walk(child, root)


def root_relative(name: str, roots: tuple[str, ...]) -> str | None:
    """소스 루트 안의 파일이면 루트 기준 posix 경로, 밖이면 None.

    symlink 를 따라가지 않은 경로로 먼저 비교한다. Git 이 보고하는 변경 경로도 링크 자신의 경로이기
    때문이다. 루트 밖 여부는 첫 경로 요소가 `..` 인지로 판단한다(`..generated` 같은 이름은 루트 안이다).
    """
    path = os.path.abspath(name)
    for base in roots:
        if os.path.splitdrive(path)[0].lower() != os.path.splitdrive(base)[0].lower():
            continue
        rel = os.path.relpath(path, base)
        if rel != "." and not os.path.isabs(rel) and Path(rel).parts[0] != "..":
            return Path(rel).as_posix()
    return None


# libclang 은 이름 없는 형식과 람다의 이름에 절대 경로를 넣는다: "(unnamed struct at /abs/a.h:3:5)".
# 그대로 두면 문서에 추출한 기계의 경로가 실리고, 기계마다 이름이 달라져 영향 분석이 이름 변경으로 본다.
_PATH_IN_NAME = re.compile(r"\(((?:unnamed|anonymous) [^()]*?|lambda) at (.+?):(\d+):(\d+)\)")


def portable_names(data: Any, roots: tuple[str, ...]) -> Any:
    """facts 의 모든 키·문자열에서 이름 속 경로를 소스 루트 기준 경로로 바꾼다.

    루트 밖 파일은 경로를 싣지 않되 이름이 겹치지 않도록 파일 이름 뒤에 전체 경로의 짧은 해시를 붙인다.
    evidence 는 원문 발췌와 그 해시를 함께 기록하므로 바꾸지 않는다(바꾸면 무결성 검사가 어긋난다).
    """
    def fix(text: str) -> str:
        def sub(m: re.Match[str]) -> str:
            path = m.group(2)
            rel = root_relative(path, roots)
            if rel is None:
                digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
                name = re.split(r"[\\/]", path)[-1]   # f-string 안의 역슬래시는 3.11 에서 문법 오류다
                rel = f"{name}#{digest}"
            return f"({m.group(1)} at {rel}:{m.group(3)}:{m.group(4)})"
        return _PATH_IN_NAME.sub(sub, text) if " at " in text else text

    if isinstance(data, str):
        return fix(data)
    if isinstance(data, dict):
        return {fix(k) if isinstance(k, str) else k: v if k == "evidence" else portable_names(v, roots)
                for k, v in data.items()}
    if isinstance(data, list):
        return [portable_names(v, roots) for v in data]
    return data


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]],
            only_files: set[str] | None = None) -> dict[str, int]:
    """entries 의 TU 를 파싱해서 model 에 주석과 위치를 채운다. 통계를 돌려준다."""
    index = cindex.Index.create()
    root = cfg.source_root.resolve()
    stats = {"tus": 0, "errors": 0, "classes": 0, "methods": 0, "functions": 0}
    seen: set[str] = set()
    # Clang 이 실제로 읽은 소스 루트 안의 파일. 범위 검사가 "분석한 빌드에서 컴파일되지 않은 파일"을
    # 가리는 근거다. include 경로는 같은 문자열이 반복되므로 해석 결과를 캐시한다.
    parsed: set[str] = set()
    resolved: dict[str, str | None] = {}

    roots = (os.path.abspath(cfg.source_root), str(root))

    def inside(name: str) -> str | None:
        if name not in resolved:
            resolved[name] = root_relative(name, roots)
        return resolved[name]

    for entry in entries:
        src, args = parse_args(entry)
        rel = relpath(str(src), root)
        if only_files is not None and rel not in only_files:
            continue
        try:
            tu = index.parse(str(src), args=args)
        except cindex.TranslationUnitLoadError as e:
            print(f"[comments] {rel}: 파싱 실패 {e}")
            stats["errors"] += 1
            continue
        stats["tus"] += 1
        if only_files is None:
            parsed.update(r for r in [inside(str(src))] + [inside(inc.include.name) for inc in tu.get_includes()] if r)
        diagnostics = [d for d in tu.diagnostics if d.severity >= cindex.Diagnostic.Error]
        stats["errors"] += len(diagnostics)
        for diagnostic in diagnostics[:10]:
            print(f"[comments] {diagnostic}")

        for cur in _walk(tu.cursor, root):
            key = f"{cur.kind.name}:{_qualified(cur)}:{cur.location.file.name}:{cur.location.line}"
            if key in seen:
                continue
            seen.add(key)

            if cur.kind in _CLASS_KINDS:
                if not cur.is_definition() or not cur.spelling:
                    continue
                name = _qualified(cur)
                ci = model.classes.get(name) or _match_by_loc(model, _loc(cur, root)) or ClassInfo(name=name)
                ci.kind = ci.kind or _CLASS_KINDS[cur.kind]
                ci.loc = ci.loc or _loc(cur, root)
                ci.brief = ci.brief or _brief(cur)
                model.classes.setdefault(ci.name, ci)
                stats["classes"] += 1

            elif cur.kind in _METHOD_KINDS and cur.semantic_parent is not None \
                    and cur.semantic_parent.kind in _CLASS_KINDS:
                cls_name = _qualified(cur.semantic_parent)
                ci = model.classes.get(cls_name)
                if ci is None:
                    continue
                m = next((x for x in ci.methods if x.name == cur.spelling), None)
                if m is None:
                    m = Method(name=cur.spelling)
                    ci.methods.append(m)
                if cur.is_definition():
                    m.def_loc = m.def_loc or _loc(cur, root)
                else:
                    m.loc = m.loc or _loc(cur, root)
                m.brief = m.brief or _brief(cur)
                stats["methods"] += 1

            elif cur.kind in _FUNCTION_KINDS:
                name = _qualified(cur)
                fn = model.functions.get(name) or FunctionInfo(name=name)
                if cur.is_definition():
                    fn.def_loc = fn.def_loc or _loc(cur, root)
                else:
                    fn.loc = fn.loc or _loc(cur, root)
                fn.brief = fn.brief or _brief(cur)
                model.functions[name] = fn
                stats["functions"] += 1

    model.meta["comments"] = stats
    if only_files is None:
        model.meta["parsed_files"] = sorted(parsed)
    return stats


def _match_by_loc(model: KnowledgeModel, loc: Location | None) -> ClassInfo | None:
    """clang-uml 은 템플릿 클래스를 Foo<T> 로 적는다. 이름이 안 맞으면 선언 위치로 찾는다."""
    if loc is None:
        return None
    for c in model.classes.values():
        if c.loc and c.loc.file == loc.file and c.loc.line == loc.line:
            return c
    return None
