"""프로젝트 용어집. 문서에 쓰인 용어의 뜻을 보여 주고, 뜻을 적지 않은 약어의 게시를 막는다.

용어집은 표시용 설정이다. 원고(Markdown)와 인용 검사, 사람 승인 상태를 바꾸지 않으므로
용어를 고쳐도 원고를 다시 생성하지 않는다. 사이트를 만들 때 문서마다 "이 문서의 용어" 표를
넣고, 전체 용어를 모은 용어집 페이지를 만든다.

약어 검사는 코드가 아닌 본문에서 대문자 2자 이상으로 된 단어(IPA, IPU3, LSC)를 찾는다.
용어집의 `terms` 나 `common` 에 없는 약어가 있으면 문서를 처음 읽는 사람이 뜻을 알 수 없으므로
게시를 중단한다. 약어가 아닌 일반 단어(파이프라인 핸들러 등)는 자동으로 찾지 못하므로
용어집에 직접 적어야 한다.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import Config

PAGE = "glossary.md"
HEADING = "이 문서의 용어"
# 펼쳐서 보여 줄 용어 수. 나머지는 접는다. 펼친 표가 길면 문서의 요약 다음에 본문이 한 화면 넘게 밀린다.
OPEN_LIMIT = 5
# 코드가 아닌 본문에서 약어로 보는 단어. 대문자로 시작하고 대문자·숫자만 이어진다(IPA, IPU3, RKISP1).
# 경계는 영숫자만 본다. 한국어 조사가 붙은 "IPA는" 도 약어로 찾고, 클래스 이름(IPAManager)과
# 식별자·경로의 일부(V4L2_CID, .YAML)는 뺀다.
ASCII_WORD = "A-Za-z0-9_"
ACRONYM = re.compile(rf"(?<![{ASCII_WORD}.-])[A-Z][A-Z0-9]+(?![{ASCII_WORD}-])")


@dataclass
class Term:
    term: str
    definition: str
    full: str = ""
    aliases: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [self.term, *self.aliases]


@dataclass
class Glossary:
    terms: list[Term]
    common: set[str]
    configured: bool

    def known(self) -> set[str]:
        return {name for t in self.terms for name in t.names()} | self.common


def glossary_file(cfg: Config) -> Path:
    return cfg.paths.get("glossary_file", cfg.config_dir / "glossary.yaml")


def load(cfg: Config) -> Glossary:
    path = glossary_file(cfg)
    if not path.is_file():
        return Glossary([], set(), False)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms = []
    seen: dict[str, str] = {}
    for i, raw in enumerate(data.get("terms", []) or []):
        term = str((raw or {}).get("term", "")).strip()
        definition = " ".join(str((raw or {}).get("definition", "")).split())
        if not term or not definition:
            raise RuntimeError(f"{path.name}: terms[{i}] 에 term 과 definition 이 모두 있어야 합니다")
        entry = Term(term, definition, str(raw.get("full", "") or "").strip(),
                     [str(a).strip() for a in (raw.get("aliases") or []) if str(a).strip()])
        for name in entry.names():
            if name in seen:
                raise RuntimeError(f"{path.name}: '{name}' 이 '{seen[name]}' 와 '{term}' 에 중복되었습니다")
            seen[name] = term
        terms.append(entry)
    common = {str(c).strip() for c in (data.get("common", []) or []) if str(c).strip()}
    overlap = sorted(common & set(seen))
    if overlap:
        raise RuntimeError(f"{path.name}: common 과 terms 에 함께 있는 용어: {', '.join(overlap)}")
    return Glossary(terms, common, True)


def prose(markdown: str) -> str:
    """코드 블록, 들여쓴 발췌, 인라인 코드, 링크 주소, HTML 주석을 뺀 본문."""
    text = re.sub(r"^---\n.*?\n---\n", "", markdown, count=1, flags=re.S)
    text = re.sub(r"^([ \t]*)(```|~~~).*?^\1\2[^\n]*$", "", text, flags=re.S | re.M)
    text = "\n".join(line for line in text.splitlines() if not re.match(r"( {4}|\t)", line))
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return re.sub(r"\{[#.][^}]*\}", "", text)


def _first(text: str, name: str) -> int | None:
    match = re.search(rf"(?<![{ASCII_WORD}-]){re.escape(name)}(?![{ASCII_WORD}-])", text)
    return match.start() if match else None


def used_terms(glossary: Glossary, markdown: str) -> list[Term]:
    """문서 본문에 나온 용어를 처음 나온 차례대로 돌려준다."""
    text = prose(markdown)
    found = []
    for t in glossary.terms:
        places = [p for p in (_first(text, n) for n in t.names()) if p is not None]
        if places:
            found.append((min(places), t))
    return [t for _, t in sorted(found, key=lambda item: item[0])]


def undefined(glossary: Glossary, pages: dict[str, str]) -> dict[str, list[str]]:
    """뜻을 적지 않은 약어 -> 그 약어가 나온 문서 목록."""
    known = glossary.known()
    found: dict[str, set[str]] = {}
    for rel, markdown in pages.items():
        for word in ACRONYM.findall(prose(markdown)):
            if word not in known:
                found.setdefault(word, set()).add(rel)
    return {word: sorted(rels) for word, rels in sorted(found.items())}


def _plain(text: str) -> str:
    """용어집의 글을 Markdown 문법이 아닌 글자 그대로 보여 준다. UQ<m, n> 이 태그로 사라지지 않게 한다."""
    return re.sub(r"([\\`*_\[\]])", r"\\\1", html.escape(text, quote=False))


def _items(terms: list[Term]) -> str:
    """표 대신 목록으로 쓴다. 휴대폰 화면에서도 뜻이 가로 스크롤 없이 줄바꿈된다."""
    return "".join(f"- **{_plain(t.term)}**" + (f" ({_plain(t.full)})" if t.full else "")
                   + f": {_plain(t.definition)}\n" for t in terms)


def block(terms: list[Term], glossary_href: str, open_limit: int = OPEN_LIMIT) -> str:
    """용어 목록. 먼저 나온 용어는 펼쳐 두고, 나머지는 접어서 본문의 첫 화면을 가리지 않게 한다.

    문서의 주제어(IPA 문서의 IPA)는 본문에 먼저 나오므로 접힌 쪽에 숨지 않는다.
    """
    if not terms:
        return ""
    text = _items(terms[:open_limit])
    rest = terms[open_limit:]
    if rest:
        text += (f'\n??? note "나머지 용어 {len(rest)}개 펼치기"\n\n'
                 + "".join("    " + line + "\n" for line in _items(rest).splitlines()))
    return (f"## {HEADING}\n\n{text}\n"
            f"다른 용어는 [용어집]({glossary_href})에서 찾을 수 있습니다.\n\n")


def insert(body: str, section: str) -> str:
    """첫 문단(문서의 요약) 바로 뒤에 넣는다. 처음 읽는 사람이 본문보다 먼저 보게 한다."""
    if not section:
        return body
    match = re.search(r"\S.*?(?:\n[ \t]*\n|\Z)", body, re.S)
    if match is None or match[0].lstrip().startswith("#"):
        return section + body
    return body[:match.end()] + ("\n" if not match[0].endswith("\n\n") else "") + section + body[match.end():]


def page(glossary: Glossary) -> str:
    return ("# 용어집\n\n**문서에 나오는 약어와 분야 용어의 뜻을 모았습니다.**\n\n"
            "각 문서의 첫머리에도 그 문서에 쓰인 용어만 따로 보여 줍니다.\n\n"
            + _items(sorted(glossary.terms, key=lambda t: t.term.casefold())))


def enforce(cfg: Config, glossary: Glossary, pages: dict[str, str]) -> None:
    """뜻이 없는 약어를 알린다. 용어집 파일이 있으면 기본으로 게시를 중단한다."""
    policy = str((cfg.raw.get("site") or {}).get("undefined_terms") or ("fail" if glossary.configured else "warn"))
    if policy not in {"fail", "warn", "off"}:
        raise RuntimeError(f"site.undefined_terms 는 fail, warn, off 중 하나여야 합니다: {policy}")
    missing = undefined(glossary, pages) if policy != "off" else {}
    if not missing:
        return
    lines = "\n".join(f"  {word}: {', '.join(rels)}" for word, rels in missing.items())
    message = (f"뜻을 적지 않은 약어가 {len(missing)}개 있습니다. {glossary_file(cfg).name} 의 terms 에 뜻을 적거나, "
               f"설명이 필요 없는 일반 약어면 common 에 추가하세요.\n{lines}")
    if policy == "fail":
        raise RuntimeError(message)
    print("경고: " + message)
