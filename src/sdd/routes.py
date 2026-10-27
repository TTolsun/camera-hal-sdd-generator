"""'지금 확인할 내용' 이동 안내 표의 문구를 정한다.

문구를 설정에 손으로 쓰면 대상 제목을 되풀이하는 행("연동 가이드에서 필요한 내용을 확인합니다")이
생긴다. 이런 행은 독자에게 새 정보를 주지 않는다. 설정에서 `q` 를 생략하면 대상 페이지의 `lead`(독자가
그 페이지에서 할 일)를 문구로 쓰고, 대상의 제목이나 `lead` 를 찾지 못하면 조용히 넘어가지 않고 실패한다.
"""
from __future__ import annotations

import re
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
