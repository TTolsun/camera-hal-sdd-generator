"""Reuse source-identical answers during impact-driven updates, never new prose."""
from __future__ import annotations

import copy
import hashlib
import re

from . import source_git
from .evidence import fingerprint, select_span


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


def earlier_scope_positions(cfg, model, section, previous):
    """Recover old coordinates for identical enclosing windows in both Git revisions."""
    if not previous:
        return None
    from .document_metadata import split_frontmatter
    metadata, _ = split_frontmatter(previous)
    base = metadata.get('source_commit')
    head = model.meta.get('source_commit')
    if base == head or any(not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)
                           for commit in (base, head)):
        return None
    files, relocated = {}, {}

    def scope_line(commit, path, scope, expected):
        key = (commit, path)
        if key not in files:
            files[key] = source_git.file_at(cfg.source_root, commit, path)
        text = files[key]
        if text is None:
            return None
        try:
            start, end = select_span(text, scope)
        except ValueError:
            return None
        if text[start:end] == expected:
            return text.count('\n', 0, start) + 1
        return None

    for topic in section['design_topics']:
        for source in topic['sources']:
            scope = source.get('scope')
            if not scope:
                continue
            key = f"{section['id']}/{topic['id']}/{source['id']}"
            record = model.evidence.get(key, {})
            context = record.get('context')
            if not context or record.get('status') != 'available' or record.get('commit') != head:
                continue
            path = source['file']
            line = scope_line(base, path, scope, context['text'])
            if line is None or line == context['line']:
                continue
            if scope_line(head, path, scope, context['text']) == context['line']:
                relocated[key] = {**record, 'context': {
                    **context, 'line': line, 'end_line': line + context['text'].count('\n'),
                }}
    if not relocated:
        return None
    earlier = copy.copy(model)
    earlier.evidence = {**model.evidence, **relocated}
    return earlier


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
        if recorded != current and recorded != (compatible_inputs or {}).get(tid):
            continue
        pinned, selected = subset(model, section, [tid])
        selected.pop('reader_profile', None)
        selected.pop('reader_family', None)
        selected.pop('reader_scope', None)
        selected_answers = copy.deepcopy(answers[tid])
        try:
            if validate:
                validate(pinned, selected, {tid: selected_answers})
        except (ValueError, TypeError, KeyError):
            continue
        retained[tid] = selected_answers
        origins[tid] = artifact.get('topic_agents', {}).get(tid, meta.get('agent', 'unknown'))
    return retained, origins
