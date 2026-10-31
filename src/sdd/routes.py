"""'지금 확인할 내용' 이동 안내 표의 문구를 정한다.

문구를 설정에 손으로 쓰면 대상 제목을 되풀이하는 행("연동 가이드에서 필요한 내용을 확인합니다")이
생긴다. 이런 행은 독자에게 새 정보를 주지 않는다. 설정에서 `q` 를 생략하면 대상 페이지의 `lead`(독자가
그 페이지에서 할 일)를 문구로 쓰고, 대상의 제목이나 `lead` 를 찾지 못하면 조용히 넘어가지 않고 실패한다.
"""
from __future__ import annotations

import re
import markdown
from markdown.inlinepatterns import BACKTICK_RE
from dataclasses import dataclass
from pathlib import Path
from .markdown_text import slugify


@dataclass(frozen=True)
class NavigationRoute:
    question: str | None
    target: str
    anchor: str | None = None

    def __post_init__(self):
        if self.anchor is not None and (not isinstance(self.anchor, str)
                                       or not self.anchor or slugify(self.anchor) != self.anchor):
            raise ValueError('routes[].anchor must be a nonempty normalized heading id')


def from_config(row):
    return NavigationRoute(str(row.get('q') or ''), str(row.get('to') or '#'), row.get('anchor'))

_BOILERPLATE = re.compile(r"(?:에서|에|을|를|의|으로|로)?(?:필요한|해당)?(?:내용|문서|절|페이지)?(?:을|를)?"
                          r"(?:확인|이동|참고|참조|열람)(?:합니다|하세요|하십시오)?")


def page_name(to: str) -> str:
    return to.split("#", 1)[0]


def resolve_title(to: str, page_titles: dict[str, str]) -> str:
    name = page_name(to)
    title = page_titles.get(name) or page_titles.get(Path(name).name)
    if not title:
        raise ValueError(f"이동 안내 대상 '{to}'의 제목을 찾지 못했습니다. 대상이 sections.yaml의 output이나 시나리오에 있어야 합니다. "
                         "페이지 slug를 링크 글자로 쓰지 않습니다.")
    return title


def derive_text(to: str, page_titles: dict[str, str], page_leads: dict[str, str]) -> str:
    """q 를 생략한 이동 안내 행의 문구: 대상 페이지에서 독자가 할 일(lead)."""
    name = page_name(to)
    lead = page_leads.get(name) or page_leads.get(Path(name).name)
    if not lead:
        raise ValueError(f"이동 안내 대상 '{to}'에 lead가 없어 문구를 만들 수 없습니다. routes[].q를 쓰거나 대상 섹션에 lead를 설정합니다.")
    return lead


def repeats_title(q: str, title: str) -> bool:
    """q 가 대상 제목에 확인·이동 같은 상투어만 붙인 문구인지 본다."""
    rest = re.sub(r"[\s.`'\"]", "", q.replace(title, ""))
    rest = _BOILERPLATE.sub("", rest)
    return len(rest) <= 2


def from_heading_content(body: str) -> list[tuple[str, str]] | None:
    """Use the section's own first prose sentence as an internal route lead.

    Table rows, code, source panels and title-only boilerplate cannot explain
    what a reader will learn. Omit such a row instead of inventing a purpose.
    Existing explicit routes and heading anchors remain unchanged.
    """
    # Use the Markdown block grammar already installed by the generator.
    # Read its tree before inline/HTML rendering, retaining code backticks in
    # prose while excluding tables, code, comments and collapsed source panels.
    parser = markdown.Markdown(extensions=['tables', 'pymdownx.details', 'pymdownx.superfences'])
    lines = body.splitlines()
    for preprocessor in parser.preprocessors:
        lines = preprocessor.run(lines)
    tree = parser.parser.parseDocument(lines).getroot()
    result, title, found = [], None, False
    for block in tree:
        if block.tag == 'h1':
            title, found = None, False
            continue
        if block.tag == 'h2':
            title, found = ''.join(block.itertext()).strip(), False
            continue
        if (not title or found or block.tag not in ('p', 'ol', 'ul')
                or title in ('소스 근거', '클래스 관계', '관련 클래스')):
            continue
        if block.tag in ('ol', 'ul'):
            item = block.find('li')
            if item is None:
                continue
            # Tight lists put prose in li.text; loose lists wrap it in p.
            # Do not summarize nested code, diagrams or subsequent steps.
            paragraph = item.find('p')
            text = item.text if item.text and item.text.strip() else (
                ''.join(paragraph.itertext()) if paragraph is not None else '')
        else:
            text = ''.join(block.itertext())
        # SuperFences may put its stash and immediately following prose into
        # one paragraph. Remove only parser placeholders, never their contents.
        text = re.sub(r'\x02[^\x03]*\x03', '', text)
        if not text.strip():
            continue
        if re.fullmatch(r'\s*\[[^\]]+\]\([^)]+\)\s*', text):
            continue  # A source/download link does not explain the topic.
        # The generated virtual-configuration notice describes scope, not the
        # topic's task. Splitting it at its first sentence also leaves an open
        # bold marker in Markdown. Use the following actual prose instead.
        from .product_context import SIMULATION_NOTICE
        if text.strip() == SIMULATION_NOTICE:
            continue
        # Sentence boundaries require whitespace after punctuation, so
        # dotted C++ members and source filenames stay whole.
        lead = re.split(r'(?<=[.!?。])\s+', ' '.join(text.split()), maxsplit=1)[0]
        if repeats_title(lead, title):
            continue
        # The table parser already protects pipes in Markdown code spans.
        # Entities inside backticks would instead display as literal text.
        pieces, cursor = [], 0
        for span in re.finditer(BACKTICK_RE, lead, re.S):
            pieces.extend([lead[cursor:span.start()].replace('|', '&#124;'), span[0]])
            cursor = span.end()
        pieces.append(lead[cursor:].replace('|', '&#124;'))
        result.append((''.join(pieces), f'#{slugify(title)}'))
        found = True
        if len(result) == 6:
            break
    return result if len(result) >= 2 else None


def warnings(sections: list[dict], page_titles: dict[str, str]) -> list[str]:
    result = []
    for sec in sections:
        anchors = set()
        for route in sec.get("routes") or []:
            parsed = from_config(route)
            if parsed.anchor is not None:
                if parsed.anchor in anchors:
                    raise ValueError('Duplicate routes[].anchor: ' + parsed.anchor)
                anchors.add(parsed.anchor)
            q, to = str(route.get("q") or ""), str(route.get("to", ""))
            title = page_titles.get(page_name(to)) or page_titles.get(Path(page_name(to)).name)
            if q and title and repeats_title(q, title):
                result.append(f"{sec['id']}: routes 문구 '{q}'는 대상 제목 '{title}'만 반복합니다. "
                              "q를 생략하면 대상 페이지의 lead로 만들고, 쓰려면 독자가 그 페이지에서 얻을 내용을 적습니다.")
    return result
