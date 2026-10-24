"""Required design questions and inspectable source contracts, independent of a project.

Coverage means an authored answer is bound to unchanged source. It does not
certify the interpretation or replace runtime validation and human approval.
"""
from __future__ import annotations

import hashlib
import re

from .evidence import contract_text, topic_blocks
from .facts.model import KnowledgeModel
from .contract_schema import configuration_errors



def audit(model: KnowledgeModel, section: dict) -> dict:
    errors = configuration_errors(section)
    if errors:
        return {"status": "incomplete", "requirements": [], "findings": errors, "human_review": "pending"}
    requirements = section.get("design_requirements", [])
    topics = section.get("design_topics", [])
    findings: list[str] = []
    ids = [r.get("id") for r in requirements]
    topic_ids = [t.get("id") for t in topics]
    if section.get("kind", "prose") != "prose":
        findings.append("design_requirements는 prose 섹션에만 사용할 수 있습니다.")
    for label, values in (("설계 항목", ids), ("설계 주제", topic_ids)):
        if any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
            findings.append(f"{label}의 id가 비었거나 중복됐습니다.")
    answers = {key: [] for key in ids}
    limits = {key: [] for key in ids}
    for topic in topics:
        tid = topic.get("id", "")
        source_ids = [s.get("id") for s in topic.get("sources", [])]
        if len(source_ids) != len(set(source_ids)):
            findings.append(f"{tid}: 근거 id가 중복됐습니다.")
        if not topic.get("title") or not topic.get("question"):
            findings.append(f"{tid}: 제목과 설계 질문이 필요합니다.")
        _, gaps = topic_blocks(model, section["id"], topic)
        _, contract_gaps = contract_text(model, section["id"], topic)
        gaps += contract_gaps
        for source in topic.get("sources", []):
            record = model.evidence.get(f"{section['id']}/{tid}/{source['id']}", {})
            text = record.get("text")
            if not isinstance(text, str) or not text.strip() or hashlib.sha256(text.encode()).hexdigest() != record.get("sha256"):
                gaps.append(f"{tid}/{source['id']}: 발췌 본문과 저장된 해시가 일치하지 않습니다.")
        findings.extend(gaps)
        for statement in topic.get("statements", []):
            covers = statement.get("covers", [])
            if not covers:
                findings.append(f"{tid}: 설명에 covers 설계 항목을 지정해야 합니다.")
            for key in covers:
                if key not in answers:
                    findings.append(f"{tid}: 정의되지 않은 설계 항목 {key}")
                elif not gaps:
                    target = limits if statement.get("kind") == "limitation" else answers
                    if tid not in target[key]:
                        target[key].append(tid)
    rows = []
    for req in requirements:
        key = req.get("id")
        if not isinstance(req.get("question"), str) or not req['question'].strip():
            findings.append(f"{key}: 설계 질문이 비었습니다.")
        state = "documented" if answers[key] else "limited" if limits[key] else "missing"
        if state != "documented":
            findings.append(f"{key}: 근거에 연결된 설계 답변이 없습니다 ({state}).")
        rows.append({"id": key, "question": req.get("question", ""), "status": state,
                     "topics": answers[key], "limitations": limits[key]})
    return {"status": "incomplete" if findings else "documented", "requirements": rows,
            "findings": list(dict.fromkeys(findings)), "human_review": "pending",
            "scope": "Required answers and unchanged source bindings; not semantic or runtime approval."}


def enforce(model: KnowledgeModel, section: dict) -> dict:
    result = audit(model, section)
    if result["findings"]:
        raise ValueError(f"{section['id']}: 설계 항목 검증 실패: " + " / ".join(result["findings"]))
    return result
