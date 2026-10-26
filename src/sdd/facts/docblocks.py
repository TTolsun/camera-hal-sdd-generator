"""선언에 붙지 않은 문서 주석 블록에서 클래스 설명을 가져온다.

libclang 은 선언 바로 앞에 붙은 주석만 그 선언의 주석으로 준다. 그런데 클래스 설명을 헤더가 아니라
구현 파일에 `\\class` / `\\struct` 블록으로 따로 적는 코드베이스가 있다. 그 블록은 어떤 선언에도 붙지
않으므로 설명이 통째로 빠진다. libcamera 에서는 `Camera`, `CameraManager`, `Request`,
`PipelineHandler` 를 포함해 클래스의 3분의 2가 설명 없이 들어왔다.

이 모듈은 그 블록을 읽어 이름이 하나로 정해질 때만 해당 클래스에 붙인다. 후보가 여럿이면 어느 것을
설명하는지 알 수 없으므로 건드리지 않는다. 선언에 붙은 주석이 이미 있으면 그대로 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from ..config import Config
from .clang_support import SourceScope
from .model import KnowledgeModel, relpath

# `/** ... */` 한 덩어리. 여는 기호가 `/**` 인 것만 문서 주석으로 본다.
_BLOCK = re.compile(r"/\*\*(.*?)\*/", re.S)
# `\class Foo` 또는 `\struct ns::Foo`. doxygen 은 `@class` 표기도 허용한다.
_TAG = re.compile(r"[\\@](class|struct)\s+([A-Za-z_][\w:]*)")
# `\brief 한 줄 설명`.
_BRIEF = re.compile(r"[\\@]brief\s+([^\n]*)")
# 같은 블록 안에서 멤버를 설명하기 시작하는 태그. 여기부터는 클래스 설명이 아니다.
_MEMBER_TAG = re.compile(r"[\\@](fn|var|typedef|enum|property|namespace|file)\b")
_JUNK = re.compile(r"^\s*\*\s?")
# 파일의 네임스페이스 선언. `using namespace X;` 와 별칭(`namespace a = b;`)은 그 파일이
# X 나 a 를 설명한다는 뜻이 아니므로 줄 머리의 여는 선언만 읽는다. C++17 의
# `namespace a::b {` 도 마디를 나눠 담는다.
_NAMESPACE = re.compile(r"^\s*(?:inline\s+)?namespace\s+([A-Za-z_][\w:]*)\b(?!\s*=)", re.M)


def _brief_text(body: str) -> str:
    r"""대상 태그 바로 뒤에 붙은 한 줄 설명만 읽는다.

    한 블록이 클래스와 그 멤버를 함께 설명하기도 한다(`\struct X` 다음에 `\fn X::y`).
    블록 전체에서 찾으면 클래스에 설명이 없을 때 멤버의 설명을 클래스 것으로 잘못 붙인다.
    """
    tag = _TAG.search(body)
    if not tag:
        return ""
    rest = body[tag.end():]
    member = _MEMBER_TAG.search(rest)
    if member:
        rest = rest[:member.start()]
    m = _BRIEF.search(rest)
    if not m:
        return ""
    return " ".join(_JUNK.sub("", m.group(1)).split())[:200]


def blocks(text: str) -> list[tuple[str, str]]:
    """문서 주석에서 (설명 대상 이름, 한 줄 설명) 을 뽑는다. 둘 다 있는 블록만 돌려준다."""
    found: list[tuple[str, str]] = []
    for match in _BLOCK.finditer(text):
        body = match.group(1)
        tag = _TAG.search(body)
        if not tag:
            continue
        brief = _brief_text(body)
        if brief:
            found.append((tag.group(2), brief))
    return found


def file_namespaces(text: str) -> frozenset[str]:
    """파일이 선언한 네임스페이스 이름의 마디 집합. `namespace a::b {` 는 {a, b} 로 담는다."""
    parts: set[str] = set()
    for name in _NAMESPACE.findall(text):
        parts.update(p for p in name.split("::") if p)
    return frozenset(parts)


def resolve(name: str, model: KnowledgeModel, near: str = "",
            namespaces: frozenset[str] = frozenset()) -> str | None:
    """설명 대상 이름을 facts 의 클래스 하나로 정한다. 하나로 정해지지 않으면 None.

    단서를 차례로 적용해 후보를 좁힌다. 단서가 후보를 전부 지우면 그 단서는 쓰지 않는다.

    1. 블록에 적힌 한정 이름 전체를 후보의 꼬리와 대조한다 (`AgcMeanLuminance::Params` 는
       `ipa::AgcMeanLuminance::Params` 에만 맞는다. 마지막 마디만 보면 중첩 클래스가 겹친다).
    2. `namespaces` 는 그 블록이 있는 파일이 선언한 네임스페이스다. 구현 파일은 자기
       네임스페이스의 클래스를 설명하므로, 한정 경로가 파일의 네임스페이스에 담기는 후보를 고른다.
    3. `near` 는 그 블록이 있는 파일의 디렉터리다. 같은 짧은 이름이 여러 네임스페이스에 있을 때
       (`ipu3::IPAContext` 와 `rkisp1::IPAContext`) 같은 디렉터리에 선언된 클래스를 고른다.

    그래도 하나로 좁혀지지 않으면 비운다. 잘못 붙이는 것보다 비워 두는 쪽이 안전하다.
    """
    if name in model.classes:
        return name
    tail = name.rsplit("::", 1)[-1]
    candidates = [n for n in model.classes if n.rsplit("::", 1)[-1] == tail]
    if "::" in name:
        qualified = [n for n in candidates if n == name or n.endswith("::" + name)]
        candidates = qualified or candidates
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    if namespaces:
        inside = [n for n in candidates
                  if all(part in namespaces for part in n.split("::")[:-1])]
        if len(inside) == 1:
            return inside[0]
        candidates = inside or candidates
    if not near:
        return None
    same_dir = [n for n in candidates
                if model.classes[n].loc and str(PurePosixPath(model.classes[n].loc.file).parent) == near]
    return same_dir[0] if len(same_dir) == 1 else None


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]]) -> dict[str, int]:
    """빌드에 들어간 파일의 문서 주석 블록으로 비어 있는 클래스 설명을 채운다."""
    scope = SourceScope(cfg.source_root, cfg.exclude)
    root = scope.root
    # 빌드에 들어간 파일만 본다: compile DB 의 translation unit 과 이미 사실에 오른 선언 파일.
    files: set[Path] = set()
    for entry in entries:
        source = Path(str(entry.get("file", "")))
        files.add(source if source.is_absolute() else Path(str(entry.get("directory", "."))) / source)
    for info in model.classes.values():
        if info.loc:
            files.add(root / info.loc.file)

    stats = {"files": 0, "blocks": 0, "filled": 0, "ambiguous": 0, "unknown": 0}
    for path in sorted(files):
        rel = relpath(str(path), root)
        if scope.is_excluded(rel) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stats["files"] += 1
        namespaces = file_namespaces(text)
        for name, brief in blocks(text):
            stats["blocks"] += 1
            target = resolve(name, model, near=str(PurePosixPath(rel).parent), namespaces=namespaces)
            if target is None:
                tail = name.rsplit("::", 1)[-1]
                key = "ambiguous" if any(n.rsplit("::", 1)[-1] == tail for n in model.classes) else "unknown"
                stats[key] += 1
                continue
            # 선언에 붙은 주석이 이미 있으면 그것이 더 가깝다. 덮어쓰지 않는다.
            if model.classes[target].brief:
                continue
            model.classes[target].brief = brief
            stats["filled"] += 1
    return stats
