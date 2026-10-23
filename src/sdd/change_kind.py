"""Deterministic classification of changes that cannot alter documented structure; no I/O.

범위 검사는 파일 단위다. 변경된 파일에 들어 있는 클래스는 그 클래스가 바뀌지 않았어도 검토
대상이 된다. 주석·공백·#include 만 바뀐 파일은 문서가 다루는 선언과 동작을 바꾸지 않으므로,
사람이나 LLM 의 판단 없이 그 사실을 기록하고 관문에서 뺀다. 판단이 애매하면 분류하지 않는다.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

CXX_SUFFIXES = {".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx", ".c++", ".inl", ".ipp", ".tpp"}

NON_SEMANTIC = "comment-whitespace-include-only"

_RAW_PREFIX = re.compile(r'(?:u8|u|U|L)?R"([^()\\\s]{0,16})\(')
_INCLUDE = re.compile(r"[ \t]*#[ \t]*include\b")
# 줄 번호가 값이 되는 코드는 주석·빈 줄만 바뀌어도 동작이 바뀐다.
_LINE_SENSITIVE = re.compile(r"\b__LINE__\b|^[ \t]*#[ \t]*line\b", re.M)


_MARK = "\x00"


def _strip(text: str) -> tuple[str, list[str]]:
    """주석을 공백으로, 리터럴을 표식으로 바꾸고 줄 이음(\\ + 줄바꿈)을 합친다.

    번역 단계 2·3 의 순서를 따른다. 원시 문자열(R"x(...)x") 안은 줄 이음도 주석도 아니다.
    리터럴은 원문 그대로 따로 돌려준다. 공백을 줄이는 단계가 리터럴 안의 공백을 건드리지 않게 하려는 것이다.
    """
    out: list[str] = []
    literals: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and text.startswith("\n", i + 1):
            i += 2                                         # 줄 이음: 논리적으로 한 줄
            continue
        raw = _RAW_PREFIX.match(text, i) if c in 'uULR' else None
        if raw and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            close = text.find(")" + raw.group(1) + '"', raw.end())
            if close < 0:
                raise ValueError("닫히지 않은 원시 문자열")
            end = close + len(raw.group(1)) + 2
            literals.append(text[i:end])
            out.append(_MARK)
            i = end
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\n":
                    raise ValueError("닫히지 않은 리터럴")
                j += 2 if text[j] == "\\" else 1
            literals.append(text[i:j + 1])
            out.append(_MARK)
            i = j + 1
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 2 if text.startswith("\\\n", i) else 1   # 줄 이음이면 다음 줄도 주석이다
            out.append(" ")
            continue
        if text.startswith("/*", i):
            close = text.find("*/", i + 2)
            if close < 0:
                raise ValueError("닫히지 않은 블록 주석")
            out.append(" ")
            i = close + 2
            continue
        if c == _MARK:
            raise ValueError("NUL 문자")
        out.append(c)
        i += 1
    return "".join(out), literals


def _normalize(text: str) -> tuple[list[str], list[str]]:
    """비교용 (줄 목록, 리터럴 목록). 줄 경계(전처리 지시문의 끝)는 지키고, 리터럴 밖의 공백만 줄인다."""
    stripped, literals = _strip(text.replace("\r\n", "\n"))
    lines, kept, k = [], [], 0
    for line in stripped.split("\n"):
        count = line.count(_MARK)
        if not _INCLUDE.match(line):              # #include "x.h" 의 리터럴도 함께 뺀다
            kept += literals[k:k + count]
            line = " ".join(line.split())
            if line:
                lines.append(line)
        k += count
    return lines, kept


def classify(path: str, old: str | None, new: str | None) -> str | None:
    """두 판의 차이가 주석·공백·#include 뿐이면 그 이유를, 아니면 None 을 돌려준다.

    추가·삭제된 파일, C/C++ 가 아닌 파일, 줄 번호를 값으로 쓰는 파일, 해석할 수 없는 파일은
    판단하지 않는다(None). 빌드 파일 한 줄이 무엇을 바꾸는지는 내용으로 알 수 없기 때문이다.
    """
    if old is None or new is None or PurePosixPath(path).suffix.lower() not in CXX_SUFFIXES:
        return None
    if _LINE_SENSITIVE.search(old) or _LINE_SENSITIVE.search(new):
        return None
    try:
        return NON_SEMANTIC if _normalize(old) == _normalize(new) else None
    except ValueError:
        return None
