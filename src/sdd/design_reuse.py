"""Reuse source-identical answers during impact-driven updates, never new prose."""
from __future__ import annotations

import copy
import hashlib

from .evidence import fingerprint


def subset(model, section, ids):
    selected = copy.deepcopy(section)
    selected['design_topics'] = [t for t in selected['design_topics'] if t['id'] in ids]
    requirements = {r for t in selected['design_topics'] for r in t['covers']}
    selected['design_requirements'] = [r for r in selected['design_requirements'] if r['id'] in requirements]
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


def reusable(model, section, previous, inputs, validate=None):
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
        if old_inputs.get(tid) != current or tid not in answers:
            continue
        pinned, selected = subset(model, section, [tid])
        selected.pop('reader_profile', None)
        selected.pop('reader_family', None)
        selected_answers = copy.deepcopy(answers[tid])
        try:
            if validate:
                validate(pinned, selected, {tid: selected_answers})
        except (ValueError, TypeError, KeyError):
            continue
        retained[tid] = selected_answers
        origins[tid] = artifact.get('topic_agents', {}).get(tid, meta.get('agent', 'unknown'))
    return retained, origins
