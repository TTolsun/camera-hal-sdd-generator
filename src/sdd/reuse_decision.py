"""Explain existing reuse gates; diagnostics never authorize compatibility.

Only identity paths and hashes are logged. Original requests and receipts stay
in their archives. A nearby checkpoint is a comparison, never a reuse fallback.
"""
import json

from .call_records import canonical_request_hash


def differences(previous, current, prefix=''):
    if isinstance(previous, dict) and isinstance(current, dict):
        result = []
        for key in sorted(previous.keys() | current.keys()):
            path = f'{prefix}.{key}' if prefix else key
            if key not in previous or key not in current:
                result.append(dict(path=path,
                    previous_sha256=canonical_request_hash(previous[key]) if key in previous else None,
                    current_sha256=canonical_request_hash(current[key]) if key in current else None))
            else:
                result.extend(differences(previous[key], current[key], path))
        return result
    if canonical_request_hash(previous) == canonical_request_hash(current):
        return []
    return [dict(path=prefix, previous_sha256=canonical_request_hash(previous),
                 current_sha256=canonical_request_hash(current))]


def reason(path):
    root = path.split('.')[0]
    if root == 'topic':
        if path == 'topic.question':
            return 'question-changed'
        if path.startswith('topic.sources'):
            return 'evidence-selection-changed'
        if path == 'topic.title':
            return 'heading-changed-current-checks-required'
        return 'answer-contract-or-unit-changed'
    return dict(source_commit='source-commit-changed', execution='cli-profile-changed',
        request='request-or-schema-changed', style_policy='global-style-changed',
        prompt_policy='writing-prompt-changed', revision='revision-policy-changed',
        validation_policy='deterministic-policy-changed', validation_model='validator-facts-changed',
        validation_answers='prior-answers-changed', grounding_policy='grounding-policy-changed',
        policy='review-or-translation-policy-changed', receipt_directory='receipt-archive-changed'
        ).get(root, 'unregistered-dependency-changed')


def scope(identity):
    """Restrict diagnostic comparisons to the same logical design unit.

    Translation text has no stable cross-edit unit ID in historical checkpoints.
    Compare the same source text only, never invent an ID across text edits.
    """
    if isinstance(identity.get('topic'), dict):
        # Historical identities have no section ID. Never attribute another
        # section's same-named topic to this one. New stores provide an explicit
        # comparison_scope outside the reuse identity, bound by the payload SHA.
        return None
    try:
        payload = json.loads(identity['request']['user'])
        if identity.get('purpose') == 'translation':
            source = payload.get('source', payload.get('texts'))
            return ('translation', canonical_request_hash(source)) if source is not None else None
        if identity.get('purpose') == 'cross-document-consistency':
            return ('consistency', payload['contract']['id'], tuple(sorted(payload['claims'])))
    except (KeyError, TypeError, ValueError):
        pass  # Legacy/retry records without a comparable scope remain explicit.
    return None


def explain(identity, candidates=(), *, verified=False):
    comparisons = []
    for path, payload in candidates:
        changes = differences(payload['identity'], identity)
        comparisons.append(dict(checkpoint=path.name,
            identity_sha256=canonical_request_hash(payload['identity']),
            receipts=list(payload.get('receipts', [])), receipts_verified=verified,
            changed_dependencies=changes,
            reason_codes=sorted({reason(change['path']) for change in changes})))
    # Several archived versions may describe the same unit. Keep every nearest
    # comparison rather than falsely calling one of them the previous run.
    if comparisons:
        minimum = min(len(row['changed_dependencies']) for row in comparisons)
        comparisons = [row for row in comparisons if len(row['changed_dependencies']) == minimum]
    codes = sorted({code for row in comparisons for code in row['reason_codes']})
    if not comparisons:
        codes = ['no-comparable-provenance']
    elif not codes:
        codes = ['identical-inputs-current-checks-required']
    return dict(current_identity_sha256=canonical_request_hash(identity),
                reason_codes=codes, comparisons=comparisons,
                comparison_only=not verified, human_review='pending')


def record(agent, key, action, explanation, *, stage='before-work', **details):
    update = getattr(agent, 'decision', None)
    if update is not None:
        update(key, dict(action=action, stage=stage, **explanation, **details))
