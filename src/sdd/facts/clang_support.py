"""Clang 추출 단계가 공유하는 커서 도구와 실행별 소스 범위."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from clang import cindex

from .. import compdb
from ..matching import glob_to_regex
from .model import Location, relpath

CLASS_KINDS = {
    cindex.CursorKind.CLASS_DECL: "class",
    cindex.CursorKind.STRUCT_DECL: "struct",
    cindex.CursorKind.CLASS_TEMPLATE: "class",
    cindex.CursorKind.ENUM_DECL: "enum",
}
METHOD_KINDS = {cindex.CursorKind.CXX_METHOD, cindex.CursorKind.CONSTRUCTOR, cindex.CursorKind.DESTRUCTOR,
                cindex.CursorKind.FUNCTION_TEMPLATE}
FUNCTION_KINDS = {cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.FUNCTION_TEMPLATE}

# 컴파일 전용 플래그. 파싱에는 필요 없고 libclang 이 거부할 수 있어 제거한다.
_DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "-Xclang", "-fdebug-compilation-dir"}
_DROP_ALONE = {"-c", "-MD", "-MMD", "-MP", "-fPIC", "-fPIE", "-pipe", "-g", "-gdwarf-4", "-gdwarf-5"}
_DROP_PREFIX = ("-O", "-Wa,", "-Wl,", "-fstack-protector", "-fuse-ld", "-flto", "-fprofile", "-fcoverage")


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


def qualified_name(cursor: cindex.Cursor) -> str:
    parts: list[str] = []
    cur = cursor
    while cur is not None and cur.kind != cindex.CursorKind.TRANSLATION_UNIT:
        if cur.kind in (cindex.CursorKind.NAMESPACE, *CLASS_KINDS) or cur == cursor:
            if cur.spelling:
                parts.append(cur.spelling)
        cur = cur.semantic_parent
    return "::".join(reversed(parts))


def cursor_location(cursor: cindex.Cursor, root: Path) -> Location | None:
    f = cursor.location.file
    if f is None:
        return None
    return Location(file=relpath(f.name, root), line=int(cursor.location.line))


class SourceScope:
    """한 추출 호출의 루트·제외 규칙과 경로 판정 캐시를 보관한다."""

    def __init__(self, root: Path, excludes: Iterable[str] = ()) -> None:
        self.root = root.resolve()
        self._excludes = tuple(glob_to_regex(p) for p in excludes)
        self._under_cache: dict[str, bool] = {}

    def is_excluded(self, relative_path: str) -> bool:
        return any(p.fullmatch(relative_path) for p in self._excludes)

    def contains(self, cursor: cindex.Cursor) -> bool:
        """소스 루트 안이면서 제외 규칙에 걸리지 않는 커서인가."""
        f = cursor.location.file
        if f is None:
            return False
        if f.name not in self._under_cache:
            try:
                relative_path = Path(f.name).resolve().relative_to(self.root).as_posix()
                inside = not self.is_excluded(relative_path)
            except ValueError:
                inside = False
            self._under_cache[f.name] = inside
        return self._under_cache[f.name]
