"""Reuse source-identical answers during impact-driven updates, never new prose."""
from __future__ import annotations

import copy
import hashlib
import re

from .evidence import contract_text, fingerprint


def _matches_previous_topic(body, pinned, section):
    """Check unchanged prose and citation files while allowing current line numbers."""
    from .product_context import scope_notice
    from .validate import extract_citations
    from .visuals import strip_blocks

    def without_line_numbers(text):
        for citation in set(extract_citations(text)):
            text = text.replace(f'`{citation}`', f"`{citation.rsplit(':', 1)[0]}`")
        return text

    topic = section['design_topics'][0]
    title = topic['title'] + '\n'
    blocks = re.split(r'^(?:## |\?\?\? note "설계 질문과 검증 범위"\s*$)', strip_blocks(body), flags=re.M)
    previous = [block.removeprefix(title).strip() for block in blocks[1:] if block.startswith(title)]
    if len(previous) != 1:
        return False
    previous_text = previous[0]
    prose, _, navigation = previous_text.rpartition('\n\n')
    link = r'\[[^\]\n]+:\d+\]\(#source-[0-9a-f]{16}\)'
    if re.fullmatch(rf'근거 원문: {link}(?: · {link})*', navigation):
        previous_text = prose
    current = without_line_numbers(previous_text)
    for layout in ({}, {'grouped': False}, {'preserve_lists': False}):
        rendered, gaps = contract_text(pinned, section['id'], topic, **layout)
        if not gaps and current == without_line_numbers((scope_notice(topic) + rendered).strip()):
            return True
    return False


def subset(model, section, ids):
    selected = copy.deepcopy(section)
    selected['design_topics'] = [t for t in selected['design_topics'] if t['id'] in ids]
    requirements = {r for t in selected['design_topics'] for r in t['covers']}
    selected['design_requirements'] = [r for r in selected['design_requirements'] if r['id'] in requirements]
    # Bind the complete scope in the input identity, but validate partial units
    # against their selected questions. The complete page checks all tasks.
    pinned = copy.copy(model)
    prefixes = tuple(f"{section['id']}/{tid}/" for tid in ids)
    pinned.evidence = {k: v for k, v in model.evidence.items() if k.startswith(prefixes)}
    return pinned, selected


def topic_inputs(model, section, policy):
    from .facts.model import KnowledgeModel
    inputs = {}
    for topic in section['design_topics']:
        pinned, selected = subset(model, section, [topic['id']])
        # Family membership is checked across the complete current guide before
        # generation/publication. It changes validation scope, not this topic's
        # drafting input; the assembled page fingerprint still binds it.
        selected.pop('reader_family', None)
        # Drafting receives the selected excerpts, not the page's class tables
        # or call graph. Structural changes must rebuild those tables without
        # unnecessarily replacing source-identical prose. The assembled page
        # retains its full structural fingerprint and answers are revalidated
        # against the current model before reuse.
        evidence_only = KnowledgeModel(evidence={
            key: {k: v for k, v in record.items() if k not in ('line', 'end_line')}
            for key, record in pinned.evidence.items()})
        inputs[topic['id']] = hashlib.sha256(
            (fingerprint(evidence_only, selected) + policy).encode()).hexdigest()
    return inputs


def reusable(model, section, previous, inputs, validate=None, *, compatible_inputs=None):
    from .document_metadata import split_frontmatter
    if not previous:
        return {}, {}
    meta, body = split_frontmatter(previous)
    artifact = meta.get('generated_design', {})
    if not isinstance(artifact, dict) or artifact.get('body_sha256') != hashlib.sha256(body.strip().encode()).hexdigest():
        return {}, {}
    answers = artifact.get('answers')
    if not isinstance(answers, dict):
        return {}, {}
    # A legacy page fingerprint does not bind prompts/model/policy. Without
    # topic input identities we cannot prove compatibility with this run.
    old_inputs = artifact.get('topic_inputs')
    if not isinstance(old_inputs, dict):
        return {}, {}
    retained, origins = {}, {}
    for tid, current in inputs.items():
        recorded = old_inputs.get(tid)
        if tid not in answers or recorded is None:
            continue
        relocated = recorded != current
        if relocated and recorded != (compatible_inputs or {}).get(tid):
            continue
        pinned, selected = subset(model, section, [tid])
        selected.pop('reader_profile', None)
        selected.pop('reader_family', None)
        selected.pop('reader_scope', None)
        selected_answers = copy.deepcopy(answers[tid])
        try:
            checked = validate(pinned, selected, {tid: selected_answers}) if validate else None
            if relocated and (checked is None or not _matches_previous_topic(body, checked[0], checked[1])):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        retained[tid] = selected_answers
        origins[tid] = artifact.get('topic_agents', {}).get(tid, meta.get('agent', 'unknown'))
    return retained, origins
