"""Required design questions and inspectable source contracts, independent of a project.

Coverage means an authored answer is bound to unchanged source. It does not
certify the interpretation or replace runtime validation and human approval.
"""
from __future__ import annotations

import hashlib
import re

from .evidence import contract_text, topic_blocks
from .facts.model import KnowledgeModel


def configuration_errors(section: dict) -> list[str]:
    errors = []
    for field in ('design_requirements', 'design_topics'):
        values = section.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            return [f'{field}는 객체 목록이어야 합니다.']
        if any(not isinstance(v.get('id'), str) or not v['id'].strip() for v in values):
            return [f'{field}의 id는 비어 있지 않은 문자열이어야 합니다.']
    for topic in section.get('design_topics', []):
        for field in ('sources', 'statements'):
            values = topic.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
                return [f"{topic['id']}/{field}는 객체 목록이어야 합니다."]
        if any(not isinstance(s.get('id'), str) or not s['id'].strip() for s in topic.get('sources', [])):
            return [f"{topic['id']}: 소스 id가 비었거나 문자열이 아닙니다."]
        for source in topic.get('sources', []):
            for field in ('file', 'start', 'end'):
                if not isinstance(source.get(field), str) or not source[field].strip():
                    errors.append(f"{topic['id']}/{source['id']}: {field}는 비어 있지 않은 문자열이어야 합니다.")
        for st in topic.get('statements', []):
            for field in ('covers', 'evidence'):
                values = st.get(field, [])
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    errors.append(f"{topic['id']}/{field}는 문자열 목록이어야 합니다.")
    from .generated_design import configuration_errors as generated_errors
    return errors + generated_errors(section)


def audit(model: KnowledgeModel, section: dict) -> dict:
    errors = configuration_errors(section)
    if errors:
        return {"status": "incomplete", "requirements": [], "findings": errors, "human_review": "pending"}
    if section.get('design_generation') == 'llm':
        return {"status": "incomplete", "requirements": [],
                "findings": ["LLM 설계 답변은 생성된 원고 기록과 함께 검증해야 합니다."], "human_review": "pending"}
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


def coverage_table(model: KnowledgeModel, section: dict) -> str:
    from .generate import slugify
    report = enforce(model, section)
    topics = {t["id"]: t for t in section["design_topics"]}
    rows = ["## 설계 항목과 근거", "",
            "아래 항목은 소스에 연결된 설명의 작성 범위를 나타냅니다. 설명의 의미와 실제 실행에 대한 승인은 별도 검토가 필요합니다.", "",
            "| 설계 질문 | 설명 위치 | 확인 범위 |", "|---|---|---|"]
    for item in report["requirements"]:
        links = ", ".join(f"[{topics[t]['title']}](#{slugify(topics[t]['title'])})" for t in item["topics"])
        label = "코드 근거와 설명 연결" + (" · 실행 확인 항목 별도" if item["limitations"] else "")
        rows.append(f"| {item['question'].replace('|', '&#124;')} | {links} | {label} |")
    return "\n".join(rows)


def source_details(model: KnowledgeModel, section: str, topic: dict) -> str:
    """Keep the original excerpt inspectable without mixing it with interpretation."""
    parts = []
    for source in topic.get("sources", []):
        record = model.evidence.get(f"{section}/{topic['id']}/{source['id']}", {})
        if record.get("status") != "available" or not record.get("text"):
            continue
        raw = record["text"]
        fence = "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", raw)), default=0))
        title = str(source["id"]).replace('"', "'").replace("\n", " ")
        body = (f"`{record['file']}:{record['line']}`에서 시작하는 발췌입니다. "
                f"종료 줄은 {record['end_line']}이며, 아래 원문을 설명과 대조할 수 있습니다.\n\n"
                f"SHA-256: `{record['sha256']}`\n\n{fence}text\n{raw}\n{fence}")
        parts.append(f'??? note "소스 근거: {title}"\n' + "\n".join("    " + line for line in body.splitlines()))
    return "\n\n".join(parts)
