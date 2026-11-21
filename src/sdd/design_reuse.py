"""Reuse source-identical answers during impact-driven updates, never new prose."""
from __future__ import annotations

import copy
import hashlib
import json
import re

from .evidence import contract_text, fingerprint


def _matches_previous_topic(body, pinned, section, *, prefix=False):
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
        if not gaps:
            expected = without_line_numbers((scope_notice(topic) + rendered).strip())
            if current == expected or (prefix and current.startswith(expected + '\n\n### ')):
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


def _part_scope(model, section, topic, parts):
    tid = topic['id']
    pinned, selected = subset(model, section, [tid])
    source_ids = {ref for part in parts for ref in part['sources']}
    narrowed = {key: value for key, value in topic.items() if key != 'reuse_parts'}
    narrowed.update(parts=parts, sources=[source for source in topic['sources'] if source['id'] in source_ids])
    selected['design_topics'] = [narrowed]
    pinned.evidence = {key: value for key, value in pinned.evidence.items()
                       if key.rsplit('/', 1)[-1] in source_ids}
    return pinned, selected, narrowed


def _part_identity(cfg, model, section, topic, parts, plan):
    from .design_request import bind_native_topic

    pinned, scoped, narrowed = _part_scope(model, section, topic, parts)
    tid = topic['id']
    prompt = plan.prompts[tid]
    identity = topic_inputs(pinned, scoped, prompt.policy + json.dumps(plan.policy))[tid]
    return bind_native_topic(cfg, pinned, section, narrowed, prompt, identity)


def reusable_prefixes(cfg, model, section, plan, reused, validate):
    """Retain a proved, separately rendered lead before the first changed part."""
    if cfg.agent.kind != 'cli':
        return {}, {}
    from .document_metadata import split_frontmatter
    meta, body = split_frontmatter(plan.previous or '')
    old = meta.get('generated_design', {})
    if not isinstance(old, dict) or old.get('body_sha256') != hashlib.sha256(body.strip().encode()).hexdigest():
        old = {}
    prefixes, bindings = {}, {}
    for topic in section['design_topics']:
        if not topic.get('reuse_parts'):
            continue
        tid, parts = topic['id'], topic['parts']
        keys = {part['id']: _part_identity(cfg, model, section, topic, [part], plan) for part in parts}
        bindings[tid] = keys
        statements = old.get('answers', {}).get(tid)
        if tid in reused or not isinstance(statements, list):
            continue
        prior = old.get('part_inputs', {}).get(tid)
        selected = []
        if isinstance(prior, dict):
            for part in parts:
                if prior.get(part['id']) != keys[part['id']]:
                    break
                selected.append(part)
            if len(selected) < len(parts):
                while selected and 'heading' not in parts[len(selected)]:
                    selected.pop()
        else:
            prior_ids = list(dict.fromkeys(row.get('part_id') for row in statements if isinstance(row, dict)))
            selected = parts[:len(prior_ids)]
            if ([part['id'] for part in selected] != prior_ids or len(selected) == len(parts)
                    or not selected or _part_identity(cfg, model, section, topic, selected, plan)
                    != old.get('topic_inputs', {}).get(tid)):
                continue
        # The unchanged lead must have a real rendering boundary so adding or
        # changing a later part cannot regroup its paragraphs.
        if not selected or len(selected) == len(parts) or 'heading' not in parts[len(selected)]:
            continue
        ids = {part['id'] for part in selected}
        values = [copy.deepcopy(row) for row in statements if isinstance(row, dict) and row.get('part_id') in ids]
        pinned, scoped, _ = _part_scope(model, section, topic, selected)
        for field in ('reader_profile', 'reader_family', 'reader_scope'):
            scoped.pop(field, None)
        try:
            checked = validate(pinned, scoped, {tid: values})
            if _matches_previous_topic(body, checked[0], checked[1], prefix=True):
                prefixes[tid] = values
        except (ValueError, TypeError, KeyError):
            continue
    return bindings, prefixes
