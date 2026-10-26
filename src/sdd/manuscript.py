"""LLM 원고의 결정적 린트: 사람이 읽기 전에 기계적으로 잡을 수 있는 집필 위반만 찾는다.

소형 모델은 집필 규칙을 확률적으로만 따르므로 프롬프트만으로는 같은 위반이 반복된다.
사실 관계와 인용은 validate.py 가 검사하고, 여기서는 문장 형태(종결어미, 대화체,
프롬프트 누설, 경로 표기)만 본다. 발견 목록은 generate 의 재요청 프롬프트에 반려
사유로 들어가고, 재시도 후에도 남으면 문서가 needs-review 로 표시된다.

omm-doc-workflow 의 manuscript-lint.mjs 이식이다. 두 가지는 이식하지 않았다:
  - 제목 수준 규칙: strip_headings 가 제목 줄을 이미 지운다.
  - 조사 붙여쓰기 교정: 이 저장소는 코드 식별자 뒤 조사를 띄어 쓴다 (prompts/section.md 예문).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, NamedTuple

from . import duplicates

_INLINE_CODE = re.compile(r"`[^`]*`")
_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_TABLE = re.compile(r"^\s*\|")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_EMPHASIS = re.compile(r"[*_]+")
# 문장 끝: 마침표/물음표/느낌표 뒤에 닫는 따옴표·괄호가 붙어도 한 문장으로 본다.
_SENT_END = re.compile(r"[.!?][\"”'’)\]]*(?=\s|$)")
# 원고 전체를 감싼 코드 펜스. 안쪽에 다른 펜스가 있어도 문자열 끝의 것만 본다.
_WRAPPED = re.compile(r"^```[A-Za-z]*[ \t]*\n(.*)\n[ \t]*```$", re.S)


@dataclass
class Finding:
    rule: str
    detail: str
    line: int  # 1부터. 규칙 위반이 줄에 없으면 0.
    text: str


class _Rule(NamedTuple):
    rule: str
    detail: str
    test: Callable[[str], object]
    sentence: bool = False  # True 면 제목·표 줄은 건너뛴다 (완성 문장이 아니어도 되므로).


def _sentences(line: str) -> list[str]:
    """문장 끝만 보기 위해 인라인 코드와 강조 기호, 목록 표식을 걷어내고 문장으로 나눈다."""
    prose = _LIST_MARK.sub("", _EMPHASIS.sub("", _INLINE_CODE.sub(" ", line)))
    return [s.strip() for s in _SENT_END.split(prose) if s.strip()]


def _bad_ending(line: str) -> bool:
    return any(re.search(r"(?<!니)다$", s) or re.search(r"(함|됨|없음|있음)$", s)
               for s in _sentences(line))


# 설계 질문을 명사절로 받아 쉼표로 이은 문장("~ 어떤 관계가 있는지는, ~ 보장하며")과 질문 어미로 끝난 문장은
# 답이 아니라 질문 문형이 본문에 새어 나온 것이다. 코드 표기 안의 물음표(`Adjusted ?`)는 보지 않는다.
_QUESTION_CLAUSE = re.compile(r"(?:는지|인지|던지|은지|을지|할지|될지|일지)(?:는|도|를|가)?\s*,")
_QUESTION_ENDING = re.compile(r"(?:습니까|입니까|나요|인가요|할까요|일까요)\s*[?]?\s*$")


def _question_leak(line: str) -> bool:
    prose = _EMPHASIS.sub("", _INLINE_CODE.sub(" ", line))
    return bool(_QUESTION_CLAUSE.search(prose) or "?" in prose
                or any(_QUESTION_ENDING.search(s) for s in re.split(r"(?<=[.!])\s+", prose.strip())))


# 한국어 문장에 한자·중국어·일본어 글자가 섞인 경우("우산術어", "闭上소")는 모델의 언어 혼입이다. 코드 표기 안은 원문이므로
# 제외하고, 본문 문장에 남은 것만 반려한다. 한국어 설명에서 한자 병기가 필요하면 코드 표기나 인용으로 쓴다.
_FOREIGN_SCRIPT = re.compile("[぀-ヿ㐀-䶿一-鿿]")


def _foreign_script(line: str) -> bool:
    return bool(_FOREIGN_SCRIPT.search(_INLINE_CODE.sub(" ", line)))


def _json_residue(line: str) -> bool:
    return bool(re.search(r'["”]\s*}+\s*$', line) or re.search(r"^\s*}+\s*$", line)
                or "\\n" in _INLINE_CODE.sub(" ", line))


_RULES = [
    _Rule("JSON 잔여물",
          '원고 본문에 JSON 포장의 흔적("}, 이스케이프된 \\n)이 남아 있습니다. Markdown 본문만 출력합니다.',
          _json_residue),
    _Rule("대화체·작업 보고",
          "독자에게 말을 걸거나 다음 단계·검토를 안내하거나 작업을 보고하는 문장은 원고가 아닙니다. 구조와 동작의 사실만 서술합니다.",
          re.compile(r"다음 단계로|추가 검토를 요구|검토를 요청|검토를 요구|이 원고는|본 원고는|요청하신|요청에 따라|확인 중이다|확인 중입니다").search),
    _Rule("원고·근거 언급",
          '독자는 요청문을 보지 못하므로 "기존 원고에 따르면", "제공된 코드에서" 같은 표현 없이 사실만 씁니다.',
          re.compile(r"기존 원고|현재 원고|이전 원고|제공된 코드|제공된 근거|제공된 자료|위 근거|아래 근거|위 코드 근거|근거 자료에 따르면").search),
    _Rule("절대 경로·줄 번호 링크",
          "코드 위치는 사실 블록에 있는 `파일:줄` 인용으로만 씁니다. file:// 링크, 절대 경로(드라이브 문자, /경로, \\\\서버), #L12 형식은 쓰지 않습니다.",
          # Unix/UNC 는 "구분자 + 비어 있지 않은 첫 성분 + 구분자" 가 있어야 경로로 본다. 첫 성분의
          # 글자 종류는 제한하지 않아 "/~user", "/-tmp", "/日本語" 도 잡되, "3 / 4", "3 /4" 같은
          # 산술식과 "//" 주석 표기는 경로로 오인하지 않는다. 한 성분짜리 "/tmp" 와 맨 루트 "/" 는
          # 놓치는 대신 오탐을 막는 절충이다.
          re.compile(r"file://|(?:^|[\s(\[`])(?:[A-Za-z]:[\\/]|/[^\s`/][^\s`]*/|\\\\[^\s`\\][^\s`]*\\)|#L\d+").search),
    _Rule("굵은 글씨 제목",
          "**굵은 글씨** 한 줄을 제목처럼 쓰지 않습니다. 제목은 파이프라인이 붙이므로 문단만 씁니다.",
          re.compile(r"^\s*\*\*[^*\n]+\*\*\s*:?\s*$").match),
    _Rule("질문 문형 누출",
          "설계 질문의 문형(\"~ 있는지는,\", \"~입니까?\")이 답변에 섞였습니다. 질문을 되풀이하지 말고 근거가 말하는 사실만 평서문으로 씁니다.",
          _question_leak, sentence=True),
    _Rule("외국 문자 혼입",
          "한국어 문장에 한자·중국어·일본어 글자가 섞였습니다. 해당 낱말을 한국어나 영어 원어로 다시 씁니다.",
          _foreign_script, sentence=True),
    _Rule("종결어미",
          '모든 문장은 "~합니다", "~입니다" 로 끝냅니다. "~한다", "~이다", "~함", "~없음" 같은 형태로 끝내지 않습니다.',
          _bad_ending, sentence=True),
]


def unwrap(text: str) -> str:
    """모델이 원고 전체를 코드 펜스로 감싼 경우 그 포장만 벗긴다. 다른 글자는 바꾸지 않는다."""
    t = text.replace("\r\n", "\n").strip()
    m = _WRAPPED.match(t)
    return (m.group(1) if m else t).strip()


_CODE_SPAN = re.compile(r"`[^`]*`")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z0-9_]+)*")


def bare_symbols(line: str, names: set[str]) -> list[str]:
    """코드 표기 밖에 나온 클래스 이름. 표기 안에 있는 이름은 건드리지 않는다."""
    outside = _CODE_SPAN.sub(" ", line)
    return [t for t in _IDENTIFIER.findall(outside) if t in names]


def lint(body: str, names: set[str] | None = None, *, check_duplicates: bool = True) -> list[Finding]:
    findings: list[Finding] = []
    fenced = False
    fence_line, fence_text = 0, ""
    for i, line in enumerate(body.replace("\r\n", "\n").split("\n")):
        if _FENCE.match(line):
            fenced = not fenced
            if fenced:
                fence_line, fence_text = i + 1, line.strip()
            continue
        if fenced:
            continue
        # 제목과 표는 완성 문장이 아니어도 되므로 문장 규칙은 건너뛴다. 나머지 규칙은 모든 줄에 적용한다.
        prose = not _HEADING.match(line) and not _TABLE.match(line)
        for r in _RULES:
            if r.sentence and not prose:
                continue
            if r.test(line):
                findings.append(Finding(r.rule, r.detail, i + 1, line.strip()))
        if prose and names:
            bare = bare_symbols(line, names)
            if bare:
                findings.append(Finding(
                    "코드 표기 없는 클래스 이름",
                    "클래스 이름은 본문에서도 코드 표기로 감쌉니다: " + ", ".join(f"`{b}`" for b in dict.fromkeys(bare)),
                    i + 1, line.strip()))
    if check_duplicates:
        for line_number, sentence, detail in duplicates.body_findings(body):
            findings.append(Finding("의미 중복 문장", detail, line_number, sentence))
    if fenced:
        # 닫히지 않은 펜스는 이후 줄 전체를 검사 불능으로 만들므로 그 자체를 위반으로 잡는다.
        findings.append(Finding("닫히지 않은 코드 펜스",
                                "코드 펜스(```)가 닫히지 않아 이후 본문을 검사할 수 없습니다. 펜스를 닫거나 코드 블록 없이 문단만 씁니다.",
                                fence_line, fence_text))
    return findings


def describe(findings: list[Finding]) -> list[str]:
    """반려 사유를 재요청 프롬프트와 검토 정보에 넣을 한 줄짜리 노트로 만든다."""
    return [f"[{f.rule}] {f.line}행 \"{_clip(f.text)}\": {f.detail}" for f in findings]


def _clip(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
