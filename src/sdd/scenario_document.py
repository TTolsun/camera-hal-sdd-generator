"""Readable scenario views over facts; never infer runtime order from a flat trace."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import asdict, dataclass

from .diagrams import scenario_call_map
from .facts.model import Message, Scenario


def fingerprint(sc: Scenario, settings: dict) -> str:
    data = {"scenario": asdict(sc), "settings": settings, "presentation_version": 2}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def hidden_message(message: Message, hide: dict) -> bool:
    # Uncertain boundaries must remain visible even if a logging rule matches.
    if message.note:
        return False
    return (any(fnmatch.fnmatchcase(owner, p) for owner in (message.src, message.dst)
                for p in hide.get("owners", []))
            or any(fnmatch.fnmatchcase(message.name, p) for p in hide.get("names", [])))


def cell(value: str) -> str:
    return value.replace("|", "&#124;").replace("\n", " ").replace("`", "&#96;")


def reference(message: Message) -> str:
    return f"`{message.loc.cite()}`" if message.loc else "위치 미확인"


def kind(message: Message) -> str:
    if message.note.startswith("예약된 호출"):
        return "메서드 전달 대상이며 동기·비동기 여부는 호출부에서 확인해야 합니다."
    if "virtual" in message.note:
        return "동적 디스패치 후보이며 실제 대상은 확인이 필요합니다."
    return message.note or "정적 호출 지점입니다."


def trace_table(messages: list[Message], start: int = 1) -> str:
    rows = ["| 기록 | 호출 측 | 대상 | 구분 | 근거 |", "|---|---|---|---|---|"]
    for index, message in enumerate(messages, start):
        rows.append(f"| {index} | `{cell(message.src)}` | `{cell(message.dst)}::{cell(message.name)}()` "
                    f"| {cell(kind(message))} | {reference(message)} |")
    return "\n".join(rows)


@dataclass
class ScenarioDocument:
    introduction: str
    overview: str
    details: str
    prompt: str
    hidden: int


def build(sc: Scenario, settings: dict, max_nodes: int = 16) -> ScenarioDocument:
    """Focus rules select evidence, not prose assertions or execution stages.

    Legacy flat facts do not carry branch ancestry. Draw a call *map*, not a
    sequence across candidates. The full extracted trace stays in this page.
    """
    hide = settings.get("hide") or {}
    shown = [m for m in sc.messages if not hidden_message(m, hide)]
    hidden = len(sc.messages) - len(shown)
    focus = settings.get("focus") or []
    groups: list[tuple[str, list[Message]]] = []
    if focus:
        for rule in focus:
            names = rule.get("names")
            if not isinstance(names, list) or not names:
                raise ValueError(f"{sc.id}: focus.names 에 호출 이름 목록이 필요합니다.")
            matches = [m for m in sc.messages
                       if any(fnmatch.fnmatchcase(m.name, p) for p in names)
                       and fnmatch.fnmatchcase(m.src, rule.get("src", "*"))
                       and fnmatch.fnmatchcase(m.dst, rule.get("dst", "*"))]
            if not matches or any(m.loc is None for m in matches):
                raise ValueError(f"{sc.id}: focus '{rule.get('title', names)}'의 호출 근거가 없습니다. "
                                 "대상 커밋의 facts와 시나리오 설정을 확인하세요.")
            groups.append((str(rule.get("title") or " / ".join(names)), matches))
    else:
        seen = set()
        for message in shown:
            key = (message.src, message.dst, message.name)
            if key in seen:
                continue
            seen.add(key)
            groups.append((f"{message.dst}::{message.name}()", [message]))
            if len(groups) == 6:
                break

    rows = ["## 주요 확인 지점", "",
            "아래 항목은 추출한 호출에서 고른 코드 탐색 지점입니다. 나열 순서는 실행 순서가 아닙니다.", "",
            "| 확인할 내용 | 호출 측과 대상 | 구분 | 근거 |", "|---|---|---|---|"]
    selected: list[Message] = []
    for title, messages in groups:
        calls = list(dict.fromkeys(f"`{cell(m.src)}` → `{cell(m.dst)}::{cell(m.name)}()`" for m in messages))
        cites = list(dict.fromkeys(reference(m) for m in messages))
        kinds = list(dict.fromkeys(kind(m) for m in messages))
        rows.append(f"| {cell(title)} | {'<br>'.join(calls)} | {'<br>'.join(kinds)} | {', '.join(cites)} |")
        selected.extend(messages)
    if not groups:
        rows.append("\n확인 필요: 표시할 호출 근거를 얻지 못했습니다. 진입점과 추출 범위를 확인하세요.")
    if selected:
        rows += ["", "## 주요 호출 관계", "",
                 "화살표는 호출 측과 대상을 연결합니다. 시간 순서나 모든 경로의 실행을 뜻하지 않습니다. "
                 "점선에는 가상 호출 후보·예약 대상 등 확인이 필요한 관계를 표시합니다.", "",
                 "```mermaid", scenario_call_map(selected, max_nodes), "```"]

    boundaries = [m for m in sc.messages if m.note]
    detail = ["## 추적 범위와 경계", "",
              f"facts에 기록된 호출은 {len(sc.messages)}개이며, 요약의 hide 규칙에 해당하는 호출은 {hidden}개입니다. "
              "전체 추적 기록에는 해당 호출도 모두 보존합니다. 기록 번호는 정적 탐색의 식별자이며 실행 순번이 아닙니다.", "",
              "조건 분기, 반복 횟수와 실제 실행 스레드는 이 호출 목록만으로 확정할 수 없습니다. "
              "가상 호출 후보는 실제 객체에 따라 선택됩니다. 예약 표시는 인자로 전달한 메서드 대상을 뜻하며, "
              "비동기 실행을 보증하지 않습니다. 호출부의 연결 방식과 동기화 계약을 확인해야 합니다."]
    if boundaries:
        # Group candidates at one call site, without asserting mutually exclusive
        # runtime branches from incomplete/legacy facts.
        by_site: dict[tuple, list[Message]] = {}
        for m in boundaries:
            key = (m.src, m.name, reference(m), kind(m))
            by_site.setdefault(key, []).append(m)
        detail += ["", "| 호출 지점 | 후보 또는 예약 대상 | 확인할 경계 | 근거 |", "|---|---|---|---|"]
        for (src, name, cite, note), messages in by_site.items():
            targets = list(dict.fromkeys(f"`{cell(m.dst)}::{cell(name)}()`" for m in messages))
            detail.append(f"| `{cell(src)}` | {'<br>'.join(targets)} | {cell(note)} | {cite} |")
    if sc.unresolved or sc.deferred:
        detail += ["", f"추출 통계: 미해결 호출 {sc.unresolved}개, 예약된 호출 {sc.deferred}개입니다."]
    detail += ["", "## 전체 추적 기록", "",
               "아래 구간을 펼치면 요약에서 제외된 호출까지 확인할 수 있습니다. "
               "이 목록은 추출 깊이 안에서 수집한 기록이며, 소스의 모든 실행 경로를 포함한다는 뜻은 아닙니다."]
    for start in range(0, len(sc.messages), 25):
        chunk = sc.messages[start:start + 25]
        detail += ["", f'??? note "추적 기록 {start + 1}–{start + len(chunk)} / {len(sc.messages)}개"', "",
                   "\n".join("    " + line for line in trace_table(chunk, start + 1).splitlines())]
    if not sc.messages:
        detail.append("\n확인 필요: 추출한 호출 기록이 없습니다.")
    overview = "\n".join(rows)
    details = "\n".join(detail)
    prompt = ("이 입력은 정적 호출 기록이며 실행 순서가 아닙니다. virtual 후보를 연속 실행으로 설명하지 않습니다. "
              "메서드 전달만으로 동기·비동기 실행을 단정하지 않습니다. 조건·스레드·소유권을 근거 없이 추측하지 않습니다.\n"
              + overview.split("## 주요 호출 관계")[0] + "\n\n" + trace_table(shown))
    introduction = (f"`{sc.entry}`에서 시작한 정적 탐색으로 호출 기록 {len(sc.messages)}개를 수집했습니다. "
                    f"주요 확인 지점 {len(groups)}개를 아래 표와 관계도에 표시합니다. "
                    "선택한 지점의 근거를 먼저 확인하고, 필요한 호출은 전체 추적 기록에서 찾아보세요.")
    if boundaries:
        introduction += (f"\n\n가상 호출 후보·예약 대상 등 확인이 필요한 경계 기록이 {len(boundaries)}개 있습니다. "
                         "추적 범위와 경계 표에서 후보를 구분한 뒤 실제 객체와 연결 방식을 확인해야 합니다.")
    return ScenarioDocument(introduction, overview, details, prompt, hidden)
