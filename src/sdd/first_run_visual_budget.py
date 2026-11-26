"""Measure complete native diagram prompts before committing first-run source choices."""
from dataclasses import replace
import hashlib
from itertools import combinations
import json

from .cli_agent import build_prompt
from .evidence_span import select_span
from .generated_visuals import inputs, schema


def visual_size(cfg, model, files, section, topic, sources, figures):
    evidence = dict(model.evidence)
    for source in sources:
        original = files[source["file"]]
        left, right = select_span(original, source)
        excerpt = original[left:right]
        evidence[f"{section['id']}/{topic['id']}/{source['id']}"] = {
            "selector": source, "status": "available", "commit": model.meta["source_commit"],
            "file": source["file"], "line": original[:left].count("\n") + 1,
            "text": excerpt, "sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        }
    candidate = replace(model, evidence=evidence)
    selected = {**section, "design_topics": [{**topic, "sources": sources}]}
    sizes = []
    for figure in figures:
        _, _, passages, system, request = inputs(cfg, candidate, selected, figure)
        response = schema(passages, request["max_nodes"], figure.get("required_symbols"),
                          figure.get("max_label_chars"), include_while=figure.get("while_conditions", False),
                          max_edge_label_chars=figure.get("max_edge_label_chars"))
        sizes.append(len(build_prompt(system, json.dumps(request, ensure_ascii=False), response)))
    return max(sizes)


def examples(selectors, measure, limit, maximum, preferred):
    """Return real sizes without declaring a size-compatible set semantically sufficient."""
    ids = list(selectors)
    groups = [preferred[:6], ids[:4], ids[2:6], ids[4:8]]
    measured = {}
    for group in groups:
        for count in range(min(maximum, len(group)), 0, -1):
            choice = next((subset for subset in combinations(group, count) if measure(subset) <= limit), None)
            if choice:
                measured[choice] = measure(choice)
                break
    if not measured:
        for candidate in ids:
            selection = (candidate,)
            if measure(selection) <= limit:
                measured[selection] = measure(selection)
                if len(measured) == 4:
                    break
    return [{"ids": ids, "diagram_chars": size} for ids, size in measured.items()]


def select(cfg, model, files, section, topic, execution, request, selectors, tag, figures, *, expand=None):
    from .first_run_catalog import MissingEvidence, SCHEMA, SYSTEM, _key, _response
    key = _key(section, topic)
    sizes = {}

    def measure(ids):
        ids = tuple(ids)
        if ids not in sizes:
            sizes[ids] = visual_size(cfg, model, files, section, topic, [selectors[i] for i in ids], figures)
        return sizes[ids]

    limit = cfg.agent.max_input_chars
    preferred = []
    maximum = 4
    details = {}
    expanded = False
    for attempt in range(cfg.max_retries + 1):
        current_request, response_schema = request, SCHEMA
        if figures:
            measured = examples(selectors, measure, limit, maximum, preferred)
            if not measured:
                raise ValueError(f"{key}: 그림 입력 한도 안에 들어가는 근거 조합이 없습니다.")
            current_request = json.dumps({
                **json.loads(request),
                "figure_selection": {
                    "max_windows": maximum, "transport_limit_chars": limit,
                    "preferred_retry_headroom_chars": min(2500, limit // 10) if cfg.max_retries else 0,
                    "measured_examples": measured, **details,
                    "note": "These combinations fit the transport limit. Select enough relevant windows for the reader decision, preserving essential conditions.",
                },
            }, ensure_ascii=False)
            response_schema = {**SCHEMA, "properties": {
                **SCHEMA["properties"], "sources": {**SCHEMA["properties"]["sources"], "maxItems": maximum},
            }}
        if len(build_prompt(SYSTEM, current_request, response_schema)) > limit:
            raise ValueError(f"{key}: 근거 선택 입력이 설정한 한도를 초과했습니다.")
        raw = execution.chat(SYSTEM, current_request, tag=f"{tag}_{attempt}", response_schema=response_schema)
        try:
            question, sources = _response(raw, key, selectors)
        except MissingEvidence as exc:
            if expanded or attempt == cfg.max_retries or not expand or not (retry := expand(selectors, exc)):
                raise
            request, selectors = retry
            preferred, details, expanded = [], {}, True
            continue
        if not figures:
            return question, sources
        preferred = [s["id"] for s in sources]
        size = measure(preferred)
        if len(sources) <= maximum and size <= limit:
            return question, sources
        maximum = max(1, min(3, len(sources) - 1))
        details = {"previous_ids": preferred, "previous_diagram_chars": size,
                   "previous_selection_exceeded_constraints": True}
    raise ValueError(f"{key}: 그림 근거 요청 {size}자가 {limit}자 한도에 맞지 않거나 선택이 너무 많습니다.")
