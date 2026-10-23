"""Deterministic classification of changes that cannot alter documented structure; no I/O.

범위 검사는 파일 단위다. 변경된 파일에 들어 있는 클래스는 그 클래스가 바뀌지 않았어도 검토
대상이 된다. 주석·공백·#include 만 바뀐 파일은 문서가 다루는 선언과 동작을 바꾸지 않으므로,
사람이나 LLM 의 판단 없이 그 사실을 기록하고 관문에서 뺀다.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

CXX_SUFFIXES = {".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx", ".inl"}

# 문자열·문자 리터럴은 그대로 두고 그 밖의 주석만 지운다. 리터럴 안의 // 를 주석으로 보면
# 코드 변경을 주석 변경으로 잘못 분류한다.
_TOKENS = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
_INCLUDE = re.compile(r"^[ \t]*#[ \t]*include\b[^\n]*$", re.M)

NON_SEMANTIC = "comment-whitespace-include-only"


def _normalize(text: str) -> str:
    text = _TOKENS.sub(lambda m: " " if m.group(0)[0] == "/" else m.group(0), text.replace("\r\n", "\n"))
    text = _INCLUDE.sub(" ", text)
    return " ".join(text.split())


def classify(path: str, old: str | None, new: str | None) -> str | None:
    """두 판의 차이가 주석·공백·#include 뿐이면 그 이유를, 아니면 None 을 돌려준다.

    추가·삭제된 파일, C/C++ 가 아닌 파일은 판단하지 않는다(None). 빌드 파일 한 줄이
    무엇을 바꾸는지는 내용으로 알 수 없기 때문이다.
    """
    if old is None or new is None or PurePosixPath(path).suffix.lower() not in CXX_SUFFIXES:
        return None
    return NON_SEMANTIC if _normalize(old) == _normalize(new) else None
