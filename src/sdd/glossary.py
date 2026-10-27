"""프로젝트 용어집. 문서에 쓰인 용어의 뜻을 보여 주고, 뜻을 적지 않은 약어의 게시를 막는다.

용어집은 표시용 설정이다. 원고(Markdown)와 인용 검사, 사람 승인 상태를 바꾸지 않으므로
용어를 고쳐도 원고를 다시 생성하지 않는다. 사이트를 만들 때 문서마다 요약 아래에 "이 문서의 용어" 를
한 줄로 접어 넣고, 전체 용어를 모은 용어집 페이지와 검색 항목, 본문 뜻 상자용 자료를 만든다.

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
# 접힌 용어 목록의 제목 줄에 보여 줄 이름 수. 더 많으면 "외 N개" 로 줄인다.
SHOWN = 4
# 코드가 아닌 본문에서 약어로 보는 단어. 대문자로 시작하고 대문자·숫자만 이어진다(IPA, IPU3, RKISP1).
# 경계는 영숫자만 본다. 한국어 조사나 하이픈이 붙은 "IPA는", "LSC-보정" 도 약어로 찾고,
# 클래스 이름(IPAManager)과 식별자·경로의 일부(V4L2_CID, .YAML, Mali-C55)는 뺀다.
ASCII_WORD = "A-Za-z0-9_"
BEFORE = r"(?<![A-Za-z0-9_.])(?<![A-Za-z0-9]-)"
AFTER = r"(?![A-Za-z0-9_]|-[A-Za-z0-9])"
ACRONYM = re.compile(rf"{BEFORE}[A-Z][A-Z0-9]+{AFTER}")


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
    anchors: dict[str, str] = {}
    for entry in terms:
        if anchor(entry) in anchors:
            raise RuntimeError(f"{path.name}: '{anchors[anchor(entry)]}' 와 '{entry.term}' 의 용어집 주소가 같습니다 "
                               "(대소문자·기호만 다른 용어)")
        anchors[anchor(entry)] = entry.term
    common = {str(c).strip() for c in (data.get("common", []) or []) if str(c).strip()}
    overlap = sorted(common & set(seen))
    if overlap:
        raise RuntimeError(f"{path.name}: common 과 terms 에 함께 있는 용어: {', '.join(overlap)}")
    return Glossary(terms, common, True)


def prose(markdown: str) -> str:
    """코드 블록, 들여쓴 발췌, 인라인 코드, 링크 주소, HTML 주석을 뺀 본문.

    들여쓴 줄은 소스 발췌로 보고 빼지만, 들여쓴 목록 항목(하위 목록)은 본문이라서 남긴다.
    """
    text = re.sub(r"^---\n.*?\n---\n", "", markdown, count=1, flags=re.S)
    text = re.sub(r"^([ \t]*)(```|~~~).*?^\1\2[^\n]*$", "", text, flags=re.S | re.M)
    text = "\n".join(line for line in text.splitlines()
                     if not re.match(r"( {4}|\t)", line) or re.match(r"\s*([-*+]|\d+\.)\s+\S", line))
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return re.sub(r"\{[#.][^}]*\}", "", text)


def _first(text: str, name: str) -> int | None:
    match = re.search(rf"{BEFORE}{re.escape(name)}{AFTER}", text)
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
    return re.sub(r"([\\`*_\[\]{}])", r"\\\1", html.escape(text, quote=False))


def anchor(term: Term) -> str:
    """용어집 페이지에서 그 용어로 바로 가는 앵커. 검색 결과와 본문의 뜻 상자가 이 주소를 쓴다."""
    return "term-" + (re.sub(r"[^\w]+", "-", term.term.casefold()).strip("-") or "x")


def _items(terms: list[Term], anchors: bool = False) -> str:
    """표 대신 목록으로 쓴다. 휴대폰 화면에서도 뜻이 가로 스크롤 없이 줄바꿈된다."""
    return "".join(f"- **{_plain(t.term)}**" + (f"{{: #{anchor(t)} }}" if anchors else "")
                   + (f" ({_plain(t.full)})" if t.full else "")
                   + f": {_plain(t.definition)}\n" for t in terms)


def block(terms: list[Term], glossary_href: str, shown: int = SHOWN) -> str:
    """요약 아래에 한 줄로 접어 두는 용어 목록.

    펼친 목록은 휴대폰에서 한 화면을 넘게 차지해 본문을 밀어낸다. 그래서 제목 줄에 앞의 몇 개
    이름만 보여 주고, 뜻은 누르면 펼친다. 본문에서 처음 나온 용어에는 사이트 스크립트가 밑줄과
    뜻 상자를 붙이므로, 읽다가 만난 용어의 뜻은 그 자리에서 볼 수 있다.
    """
    if not terms:
        return ""
    names = ", ".join(t.term for t in terms[:shown])
    rest = f" 외 {len(terms) - shown}개" if len(terms) > shown else ""
    title = f"{HEADING}: {names}{rest}".replace('"', "'")
    inner = _items(terms) + f"\n다른 용어는 [용어집]({glossary_href})에서 찾을 수 있습니다.\n"
    return f'??? page-terms "{title}"\n\n' + "".join(("    " + line) if line else "" for line in inner.splitlines(True)) + "\n"


def insert(body: str, section: str) -> str:
    """첫 문단(문서의 요약) 바로 뒤에 넣는다. 처음 읽는 사람이 본문보다 먼저 보게 한다."""
    if not section:
        return body
    match = re.search(r"\S.*?(?:\n[ \t]*\n|\Z)", body, re.S)
    # 제목·코드 블록·HTML 블록으로 시작하면 빈 줄이 블록 안에 있을 수 있으므로 맨 앞에 넣는다.
    if match is None or match[0].lstrip().startswith(("#", "```", "~~~", "<", "???")):
        return section + body
    return body[:match.end()] + ("\n" if not match[0].endswith("\n\n") else "") + section + body[match.end():]


def _group(term: Term) -> str:
    """용어집 바로가기의 묶음. 영문은 첫 글자, 한글은 첫 자음, 숫자는 0–9."""
    first = term.term[0]
    if "가" <= first <= "힣":
        return "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[(ord(first) - ord("가")) // 588]
    if first.isdigit():
        return "0–9"
    return first.upper()


def page(glossary: Glossary) -> str:
    """전체 용어집. 맨 위의 바로가기가 각 묶음의 첫 용어로 이동한다.

    묶음마다 제목을 달면 한두 개짜리 묶음이 많아 페이지가 제목으로 길어진다. 그래서 목록은
    하나로 두고, 바로가기만 묶음 단위로 만든다.
    """
    def order(t: Term) -> tuple[int, str]:
        # 숫자, 영문, 한글 순서. 같은 묶음 안에서는 대소문자를 구분하지 않고 정렬한다.
        group = _group(t)
        return (0 if group == "0–9" else 2 if "ㄱ" <= group <= "ㅎ" else 1, t.term.casefold())

    terms = sorted(glossary.terms, key=order)
    firsts: dict[str, Term] = {}
    for t in terms:
        firsts.setdefault(_group(t), t)
    jump = " · ".join(f"[{g}](#{anchor(t)})" for g, t in firsts.items())
    return ("# 용어집\n\n**문서에 나오는 약어와 분야 용어의 뜻을 모았습니다.**\n\n"
            "본문에서 밑줄이 그어진 용어를 누르면 그 자리에서 뜻을 볼 수 있습니다. "
            "문서 찾기에서 용어 이름으로 검색할 수도 있습니다.\n\n"
            f"바로가기: {jump}\n\n{_items(terms, anchors=True)}")


def search_entries(glossary: Glossary, page_title: str) -> list[dict]:
    """문서 찾기에 넣을 용어 항목. 누르면 용어집의 그 용어로 이동한다."""
    url = PAGE.removesuffix(".md") + ".html#"
    # 다른 표기(파이프라인 핸들러)로 찾아도 나오도록 제목 뒤에 붙인다.
    return [{"title": t.term + (f" ({t.full})" if t.full else "") + (f" · {', '.join(t.aliases)}" if t.aliases else ""),
             "page": page_title, "url": url + anchor(t)}
            for t in glossary.terms]


def data(glossary: Glossary) -> list[dict]:
    """사이트 스크립트가 본문 용어에 밑줄과 뜻 상자를 붙일 때 읽는 자료(assets/glossary.json)."""
    return [{"id": anchor(t), "term": t.term, "names": t.names(), "definition": t.definition}
            for t in glossary.terms]


def enforce(cfg: Config, glossary: Glossary, pages: dict[str, str]) -> None:
    """뜻이 없는 약어를 알린다. 용어집 파일이 있으면 기본으로 게시를 중단한다."""
    policy = cfg.site.undefined_terms
    if policy is None:
        policy = "fail" if glossary.configured else "warn"
    # YAML 은 따옴표 없는 off 를 false 로 읽는다. 끄려던 설정이 기본값(fail)으로 바뀌지 않게 한다.
    policy = "off" if policy is False else str(policy)
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
