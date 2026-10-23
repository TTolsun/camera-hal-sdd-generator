"""Shared path globs and case-sensitive C++ symbol selection; no I/O."""

import fnmatch
import re


def is_anonymous(class_name: str) -> bool:
    """libclang 이 익명 구조체·공용체에 붙이는 이름인지 판정한다.

    이 이름에는 파싱한 기계의 절대 경로와 줄 번호가 들어 있다
    (`Ctx::(unnamed struct at /home/…/ipa_context.h:33:2)`). 설정의 어떤 패턴으로도 고를 수 없고,
    줄이 밀리면 다른 이름이 되어 같은 구조체가 둘로 보인다.
    """
    return "(unnamed " in class_name or "(anonymous " in class_name


def matches_symbol(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) or fnmatch.fnmatchcase(name.rsplit("::", 1)[-1], p) for p in patterns)


def package_of(file: str, depth: int) -> str:
    """패키지 = 선언 파일 경로의 앞 depth 개 디렉터리.

    clang-uml 의 package_type: directory 와 같은 규칙이되, 깊이를 설정으로 정한다.
    경로가 depth 보다 얕으면 그 파일이 들어 있는 디렉터리까지만 쓰고, 루트 바로 아래 파일은
    "(root)" 로 묶는다. 깊이를 올려도 얕은 트리가 빈 이름을 만들지 않게 하려는 처리다.
    """
    parts = file.replace("\\", "/").split("/")
    if len(parts) > depth:
        return "/".join(parts[:depth])
    return "/".join(parts[:-1]) or "(root)"


def package_selected(name: str, patterns: list[str]) -> bool:
    """패키지 이름 glob. 경로 구분자를 특별히 다루지 않으므로 `src/*` 는 `src/ipa/ipu3` 에도 걸린다."""
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**/` 는 0개 이상의 디렉터리, `*` 는 슬래시를 넘지 않는 glob 을 정규식으로 바꾼다."""
    out = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def match_any(path: str, globs: list[str]) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)
