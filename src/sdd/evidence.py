"""Revision-pinned source excerpts for configured design questions.

Anchors select source text, never a guessed line range in the current checkout.
Missing/ambiguous anchors remain explicit review tasks. No LLM approves evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import PurePosixPath

from .config import Config
from .facts.model import KnowledgeModel


# 문서에 실리는 내용에는 영향이 없고, 페이지 배치와 영향 분석에만 쓰는 설정.
# 지문에 넣으면 메뉴 분류나 다음 문서 링크만 바꿔도 근거가 달라진 것으로 판정되어,
# 근거가 고정된 문서를 모델로 다시 만들어야 한다.
#   group  - 사이트 왼쪽 메뉴에서 묶을 제목
#   nav_section - 독자 그룹 안의 작업별 소분류
#   routes - "지금 확인할 내용" 표
#   next   - 페이지 끝의 다음 문서 링크
#   watch  - 재생성 대상을 고르는 경로 glob
_PRESENTATION_KEYS = ("group", "nav_section", "routes", "next", "watch")


def requires_fingerprint(section: dict) -> bool:
    return bool(section.get("semantic_review") or section.get("design_topics") or section.get("design_requirements") or section.get("reader_profile")
                or section.get("narration") == "facts")


def select_span(text: str, source: dict) -> tuple[int, int]:
    """Select a unique passage inside an optional uniquely anchored scope."""
    offset, region = 0, text
    if 'scope' in source:
        scope = source['scope']
        offset, limit = select_span(text, scope)
        region = text[offset:limit]
    start, end = source['start'], source['end']
    if not start or not end or region.count(start) != 1:
        raise ValueError('시작 앵커가 없거나 유일하지 않습니다.')
    begin = region.index(start)
    finish = region.find(end, begin + len(start))
    if finish < 0:
        raise ValueError('종료 앵커가 선택 범위 안에 없습니다.')
    return offset + begin, offset + finish + len(end)


def collect(cfg: Config, model: KnowledgeModel) -> None:
    from .contract_schema import configuration_errors

    sections = cfg.sections()
    from .reader_profiles import family_errors
    options = cfg.documentation.settings()
    if errors := family_errors(sections, options.get('features', []), enabled=options.get('enabled', False)):
        raise ValueError(' / '.join(errors))
    # Fail before Git reads or replacing evidence, including the CLI path that
    # collects excerpts before Generator.run validates required answers.
    for sec in sections:
        errors = configuration_errors(sec)
        if errors:
            raise ValueError(f"{sec['id']}: 설계 설정 오류: " + " / ".join(errors))
    records = {}
    commit = str(model.meta.get("source_commit", ""))
    cache = {}
    for sec in sections:
        for topic in sec.get("design_topics", []):
            for source in topic.get("sources", []):
                key = f"{sec['id']}/{topic['id']}/{source['id']}"
                record = {"commit": commit, "selector": source, "status": "needs-review"}
                records[key] = record
                file = str(source["file"])
                try:
                    if not re.fullmatch(r"[0-9a-f]{40}", commit):
                        raise ValueError("facts에 불변 Git 커밋이 없습니다.")
                    if source.get('kind') == 'product':
                        from .product_context import record as product_record
                        records[key] = product_record(source, commit)
                        continue
                    if PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts or ":" in file or "\\" in file:
                        raise ValueError("소스 루트 상대 경로가 필요합니다.")
                    if file not in cache:
                        # ./ makes Git resolve relative to source_root, including repository subdirectories.
                        result = subprocess.run(["git", "show", f"{commit}:./{file}"], cwd=cfg.source_root,
                                                capture_output=True, encoding="utf-8")
                        if result.returncode:
                            raise ValueError("해당 커밋에서 근거 파일을 읽을 수 없습니다.")
                        cache[file] = result.stdout
                    text = cache[file]
                    begin, finish = select_span(text, source)
                    excerpt = text[begin:finish]
                    if len(excerpt) > int(source.get("max_chars", 12000)):
                        raise ValueError("근거 발췌가 허용 길이를 초과했습니다.")
                    line = text[:begin].count("\n") + 1
                    record.update(status="available", file=file, line=line,
                                  end_line=line + excerpt.count("\n"), text=excerpt,
                                  sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
                                  # 발췌 밖에 공백뿐이면 파일 전체를 고정한 근거다. 범위 검사가 이 표시를 쓴다.
                                  whole_file=not text[:begin].strip() and not text[finish:].strip())
                    if 'scope' in source:
                        left, right = select_span(text, source['scope'])
                        context = text[left:right]
                        first = text[:left].count('\n') + 1
                        record['context'] = {'text': context, 'sha256': hashlib.sha256(context.encode()).hexdigest(),
                                             'line': first, 'end_line': first + context.count('\n')}
                    if source.get("sha256") and record["sha256"] != source["sha256"]:
                        record.update(status="needs-review", reason="근거 본문이 변경됐습니다. 연결된 설계 설명을 재검토하세요.")
                except (OSError, ValueError) as exc:
                    record["reason"] = str(exc)
    model.evidence = records


def topic_blocks(model: KnowledgeModel, section: str, topic: dict) -> tuple[list, list[str]]:
    from .budget import Block
    blocks, gaps = [], []
    for source in topic.get("sources", []):
        key = f"{section}/{topic['id']}/{source['id']}"
        record = model.evidence.get(key, {})
        if (record.get("status") != "available" or record.get("commit") != model.meta.get("source_commit")
                or record.get("selector") != source):
            gaps.append(f"{key}: {record.get('reason', '현재 설정·커밋에 맞는 근거가 없습니다.')}")
            continue
        blocks.append(Block(key, f"소스 발췌 `{record['file']}:{record['line']}`\n{record['text']}", 1))
    if not topic.get("sources"):
        gaps.append(f"{section}/{topic['id']}: 근거 선택이 없습니다.")
    return blocks, gaps


# 한 문단에 모으는 문장 수와 길이의 상한. reader_profiles 의 밀집 문단 검사(600자·4문장)보다 낮게 둔다.
PARAGRAPH_SENTENCES = 4
PARAGRAPH_CHARS = 480


def _sentence_count(text: str) -> int:
    return max(1, len(re.findall(r"[.!?](?=" + chr(92) + "s|$)", re.sub(r"`[^`]*`", " ", text))))


def _paragraphs(entries: list[tuple[str, str, list[str]]], *, grouped: bool = True, preserve_lists: bool = True) -> list[str]:
    """설명 문장을 문단으로 묶는다. 같은 주제의 이어지는 설명 2~4문장이 한 문단이 되고 인용은 문단 끝에 모은다.

    문장마다 근거는 그대로 연결되어 있다(답변 기록의 evidence·quote). 여기서는 표시만 묶으며
    실행 확인 항목(limitation)은 사실 서술과 섞지 않고 따로 둔다."""
    paragraphs: list[str] = []
    group: list[str] = []
    cites: list[str] = []
    sentences = 0
    kind = 'behavior'

    def flush():
        nonlocal group, cites, sentences
        if group:
            prefix = '실행 확인 항목: ' if kind == 'limitation' else ''
            citations = list(dict.fromkeys(cites)) if grouped else cites
            paragraphs.append(prefix + ' '.join(group) + ' ' + ', '.join(citations))
        group, cites, sentences = [], [], 0

    for entry_kind, text, citations in entries:
        count = _sentence_count(text)
        if group and (not grouped or entry_kind != kind or entry_kind == 'limitation'
                      or (preserve_lists and (re.match(r'\d+\.\s', text) or re.match(r'\d+\.\s', group[0])))
                      or sentences + count > PARAGRAPH_SENTENCES
                      or sum(len(t) for t in group) + len(text) > PARAGRAPH_CHARS):
            flush()
        kind = entry_kind
        group.append(text)
        cites.extend(citations)
        sentences += count
    flush()
    return paragraphs


def summary_parts(topic: dict) -> set[str]:
    """Part IDs whose answers open the topic as its summary paragraph."""
    return {p['id'] for p in topic.get('parts', []) if isinstance(p, dict) and p.get('role') == 'summary'}


def contract_text(model: KnowledgeModel, section: str, topic: dict, *, grouped: bool = True, preserve_lists: bool = True) -> tuple[str, list[str]]:
    """Render authored statements only while every linked excerpt matches its pin.

    A pin verifies unchanged source, not the truth of the authored interpretation.
    Human approval is deliberately not represented by this mechanism.
    grouped=False preserves the old one-paragraph-per-statement layout.
    """
    if type(grouped) is not bool:
        raise ValueError('grouped must be a boolean')
    if type(preserve_lists) is not bool:
        raise ValueError('preserve_lists must be a boolean')
    entries, gaps = [], []
    sources = {s['id']: s for s in topic.get('sources', [])}
    summaries = summary_parts(topic)
    for statement in topic.get('statements', []):
        if not isinstance(statement.get('text'), str) or not statement['text'].strip():
            gaps.append('비어 있는 설계 설명이 있습니다.')
        if statement.get('kind', 'behavior') not in ('behavior', 'limitation'):
            gaps.append('설계 설명의 kind는 behavior 또는 limitation이어야 합니다.')
        citations = []
        for ref in statement.get('evidence', []):
            source = sources.get(ref, {})
            record = model.evidence.get(f"{section}/{topic['id']}/{ref}", {})
            if (not source.get('sha256') or record.get('status') != 'available'
                    or record.get('sha256') != source['sha256']
                    or record.get('selector') != source
                    or record.get('commit') != model.meta.get('source_commit')):
                gaps.append(f"{ref}: 설계 설명과 연결된 근거 지문이 없거나 일치하지 않습니다.")
            else:
                citations.append(f"`{record['file']}:{record['line']}`")
        if not statement.get('evidence'):
            gaps.append('근거가 연결되지 않은 설계 설명이 있습니다.')
        # 요약은 뒤의 상세 설명과 한 문단으로 묶지 않는다. 표시 종류만 다르고 근거 검사는 같다.
        # 실행 확인 항목은 요약이라도 표지를 유지한다(생성기는 요약을 behavior로 고정한다).
        kind = statement.get('kind', 'behavior')
        if statement.get('part_id') in summaries and kind == 'behavior':
            kind = 'summary'
        entries.append((kind, str(statement.get('text', '')), citations))
    paragraphs = _paragraphs(entries, grouped=grouped, preserve_lists=preserve_lists)
    if not paragraphs:
        gaps.append('설계 설명이 없습니다.')
    return ('확인 필요: ' + ' / '.join(gaps) if gaps else '\n\n'.join(paragraphs)), gaps


def fingerprint(model: KnowledgeModel, sec: dict) -> str:
    """Invalidate carryover for changed structure, excerpts or question configuration."""
    from .matching import matches_symbol
    names = {n for n in model.classes if matches_symbol(n, sec.get("facts", {}).get("classes", []))}
    serialized = model.to_dict()
    section = {k: v for k, v in sec.items() if k not in _PRESENTATION_KEYS}
    data = {"section": section, "classes": {n: serialized["classes"][n] for n in sorted(names)},
            "functions": {n: v for n, v in serialized["functions"].items()
                          if matches_symbol(n, sec.get("facts", {}).get("functions", []))},
            "relations": sorted((r.source, r.target, r.type) for r in model.relations if r.source in names),
            # whole_file 은 범위 검사용 표시다. 원고의 입력이 아니므로 넣지 않는다(넣으면 생성기만 올려도 지문이 바뀐다).
            "evidence": {k: {f: v for f, v in r.items() if f not in ("commit", "whole_file")}
                         for k, r in model.evidence.items() if k.startswith(sec["id"] + "/")}}
    facts = sec.get("facts", {})
    if facts.get("packages") or sec.get("kind") == "per-package":
        data["packages"] = serialized["packages"]
    if facts.get("packages"):
        # Package dependency tables consume all relations and class memberships.
        data["package_dependencies"] = serialized["relations"]
        data["class_packages"] = {n: c.package for n, c in model.classes.items()}
    if facts.get("reading_order"):
        data["reading_order"] = serialized["scenarios"].get(str(facts["reading_order"]))
    if sec.get('scenario'):
        data['scenario'] = serialized['scenarios'].get(sec['scenario'])
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
