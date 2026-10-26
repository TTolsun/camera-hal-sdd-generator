"""같은 절 안에서 같은 근거를 같은 뜻으로 되풀이한 문장을 결정적으로 찾는다.

모델은 근거 구절마다 한 문장씩 쓰도록 요청받기 때문에, 질문이 겹치면 같은 구절에서 같은 사실을
말만 바꿔 두 번 쓴다. 이 모듈은 의미를 이해하지 않는다. 같은 근거 발췌를 인용하면서 내용어
(코드 식별자와 한글 낱말의 앞 두 글자)가 대부분 겹치는 문장만 중복 후보로 본다. 찾은 문장은 조용히
지우지 않고 재요청 사유로 돌려준다.
"""
from __future__ import annotations

import re
from typing import Iterable

from .validate import extract_citations

# 비교에서 뺄 서술·연결 표현. 문장마다 나오므로 겹쳐도 같은 사실의 증거가 아니다.
_FUNCTION_WORDS = frozenset(
    "합니다 입니다 있습니다 없습니다 하며 해야 있는 하는 수행 대한 통해 위해 경우 또는 그리고 이는 이를 해당 "
    "모든 각각 따라서 대해 같은 때문 하여 됩니다 되며 않습니다 않아야 사용하여 사용 호출 함수 이때 그러나 "
    "아니라 있으며 있을 없으며 한다 된다 하고 하면 하지 해서는".split())
_CITATION = re.compile(r"`[^`\n]*\.[A-Za-z]+:\d+`")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z0-9_]+)*(?:\(\))?")

# 실제 중복과 같은 근거를 다른 각도로 쓴 문장을 가른 값이다. 낮추면 같은 발췌의 서로 다른 조건 문장까지
# 반려하고, 높이면 말만 바꾼 문장을 놓친다. 공개 libcamera 문서에서 찾은 중복 문장 쌍은 0.75 이상이었고
# 구분되는 쌍은 0.67 이하였다.
SIMILARITY = 0.7
MINIMUM_SHARED = 6


def content_tokens(text: str) -> frozenset[str]:
    """문장의 내용어 집합: 코드 식별자(마지막 성분, 소문자)와 한글 낱말 앞 두 글자."""
    text = _CITATION.sub(" ", text)
    names = {m.removesuffix("()").rstrip("_").split("::")[-1].lower() for m in _IDENTIFIER.findall(text)}
    words = {w[:2] for w in re.findall(r"[가-힣]{2,}", text) if w not in _FUNCTION_WORDS}
    return frozenset(names | words)


def similar(left: str, right: str, *, threshold: float = SIMILARITY, minimum: int = MINIMUM_SHARED) -> bool:
    a, b = content_tokens(left), content_tokens(right)
    shared = len(a & b)
    return bool(a and b) and shared >= minimum and shared / min(len(a), len(b)) >= threshold


def _clip(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def statement_findings(model, section_id: str, answers: dict[str, list[dict]],
                       *, only_after: dict[str, int] | None = None) -> list[str]:
    """설계 답변 문장 사이의 중복. 앞 문장과 뜻이 겹치는 뒤 문장을 반려 사유로 돌려준다.

    only_after 가 있으면 주제별로 그 개수 뒤에 온 문장만 뒤 문장으로 본다. 재요청 때 이미 통과한
    앞 문장끼리의 관계는 다시 지적하지 않고, 새로 추가한 문장만 검사하기 위해 쓴다.
    """
    def evidence_ids(topic_id: str, statement: dict) -> frozenset[str]:
        ids = set()
        for ref in statement.get("evidence", []) or []:
            record = model.evidence.get(f"{section_id}/{topic_id}/{ref}", {})
            ids.add(record.get("sha256") or f"{topic_id}/{ref}")
        return frozenset(ids)

    seen: list[tuple[str, int, str, frozenset[str]]] = []
    findings: list[str] = []
    for topic_id, statements in answers.items():
        start = (only_after or {}).get(topic_id, 0)
        for index, statement in enumerate(statements or []):
            text = statement.get("text") if isinstance(statement, dict) else None
            if not isinstance(text, str):
                continue
            evidence = evidence_ids(topic_id, statement)
            if index >= start:
                for other_topic, other_index, other_text, other_evidence in seen:
                    if evidence & other_evidence and similar(text, other_text):
                        findings.append(
                            f"[의미 중복] {topic_id} {index + 1}번째 설명이 앞의 {other_topic} {other_index + 1}번째 "
                            f"설명과 같은 근거로 같은 내용을 되풀이합니다: \"{_clip(text)}\" ≈ \"{_clip(other_text)}\". "
                            "앞 설명에 없는 조건·예외·호출 책임만 쓰고, 새로 쓸 내용이 없으면 이 질문의 범위를 좁혀 다시 답합니다.")
                        break
            seen.append((topic_id, index, text, evidence))
    return findings


def body_findings(body: str) -> list[tuple[int, str, str]]:
    """모델이 쓴 본문(문단 끝에 인용이 붙은 Markdown)에서 같은 인용을 공유하는 중복 문장을 찾는다.

    반환값은 (뒤 문장의 시작 행, 문장, 반려 사유)이다."""
    paragraphs: list[tuple[int, str, frozenset[str]]] = []
    fenced = False
    for number, block in _blocks(body):
        if block.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or re.match(r"^\s*(?:#|\||[-*+]\s|\d+\.\s)", block):
            continue
        citations = frozenset(extract_citations(block))
        if citations:
            paragraphs.append((number, block, citations))
    findings: list[tuple[int, str, str]] = []
    sentences: list[tuple[int, str, frozenset[str]]] = []
    for number, block, citations in paragraphs:
        for sentence in _sentences(block):
            for other_number, other, other_citations in sentences:
                if citations & other_citations and similar(sentence, other):
                    findings.append((number, sentence,
                                     f"{other_number}행의 문장과 같은 근거로 같은 내용을 되풀이합니다. "
                                     "앞 문장에 없는 조건·예외·호출 책임만 쓰고 같은 설명은 한 번만 씁니다."))
                    break
            sentences.append((number, sentence, citations))
    return findings


def _blocks(body: str) -> Iterable[tuple[int, str]]:
    start, lines = 0, []
    for number, line in enumerate(body.replace("\r\n", "\n").split("\n"), 1):
        if line.strip():
            if not lines:
                start = number
            lines.append(line)
        elif lines:
            yield start, "\n".join(lines)
            lines = []
    if lines:
        yield start, "\n".join(lines)


def _sentences(block: str) -> list[str]:
    text = _CITATION.sub(" ", " ".join(block.split()))
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 12]


def repeated_topics(model, section: dict, answers: dict[str, list[dict]]) -> list[str]:
    """재사용하려는 이전 답변 중, 앞 주제와 뜻이 겹쳐 다시 만들어야 하는 주제의 id.

    이전 원고에 중복이 남아 있으면 절 전체 검사가 마지막에 생성을 실패시키므로, 뒤쪽 주제를 재사용에서
    빼서 같은 실행 안에서 다시 쓰게 한다."""
    kept: dict[str, list[dict]] = {}
    dropped: list[str] = []
    for topic in section["design_topics"]:
        tid = topic["id"]
        if tid not in answers:
            continue
        trial = {**kept, tid: answers[tid]}
        skip = {key: len(value) for key, value in kept.items()}
        if statement_findings(model, section["id"], trial, only_after=skip):
            dropped.append(tid)
        else:
            kept[tid] = answers[tid]
    return dropped
