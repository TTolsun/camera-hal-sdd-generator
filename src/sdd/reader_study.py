"""Summarize recorded reader studies; never infer human responses from agents.

python -m sdd.reader_study --protocol protocol.json --results human-results.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


def validate_protocol(protocol: dict, artifact_hashes: dict) -> None:
    participants = protocol['participants']
    ids = [p['id'] for p in participants]
    base = protocol['base_tasks']
    if (len(ids) < 3 or len(set(ids)) != len(ids) or len(base) < 6 or len(set(base)) != len(base)
            or not {'new_developer', 'other_team'} <= {p['perspective'] for p in participants}
            or protocol['minimum_base_successes'] != 5 or protocol['minimum_ease_median'] != 4
            or protocol['task_timeout_seconds'] != 600 or protocol['interruption_seconds'] != 300):
        raise ValueError('Protocol changes the fixed participant, task or acceptance criteria.')
    assigned = []
    for participant in participants:
        tasks = participant['tasks']
        if (len(tasks) != len(set(tasks)) or not {'S', 'R', 'X'} <= set(tasks)
                or len(set(tasks) & set(base)) != 2 or set(tasks) - set(base) - {'S', 'R', 'X'}):
            raise ValueError('Every participant needs two base tasks plus S, R and X.')
        assigned.extend(task for task in tasks if task in base)
    if set(assigned) != set(base):
        raise ValueError('All fixed base tasks must be represented; repeated participants remain assigned.')
    artifacts = protocol['artifacts']
    if not {'instructions', 'participant', 'rubric', 'baseline', 'legacy_rubric'} <= set(artifacts):
        raise ValueError('Protocol must bind instructions, participant packet, rubrics and baseline.')
    if any(artifact_hashes.get(key) != entry['sha256'] for key, entry in artifacts.items()):
        raise ValueError('Frozen instructions, rubric or baseline changed; do not mix observations.')


def summarize(protocol: dict, rows: list[dict], *, protocol_sha256: str, artifact_hashes: dict,
              manifest_observations: dict) -> dict:
    """Check provenance/completeness before aggregating manual task judgments.

    `correct` is an assessor's judgment, not a semantic classifier. Participant
    provenance remains a declaration to be checked by the study facilitator.
    """
    validate_protocol(protocol, artifact_hashes)
    expected = {(p['id'], task): p for p in protocol['participants'] for task in p['tasks']}
    seen = {}
    for row in rows:
        key = row['participant_id'], row['task_id']
        if key not in expected or key in seen:
            raise ValueError(f'Unexpected or duplicate assignment: {key}')
        if row.get('source_kind') != 'human':
            raise ValueError('Agent/synthetic records cannot enter the human study.')
        if row.get('build_id') != protocol['build_id']:
            raise ValueError(f'Mixed or missing build_id: {key}')
        if row.get('protocol_sha256') != protocol_sha256:
            raise ValueError(f'Stale or missing protocol fingerprint: {key}')
        if row.get('perspective') != expected[key]['perspective']:
            raise ValueError(f'Changed participant perspective: {key}')
        seen[key] = row

    pending, outcomes, ease, interest, naturalness = [], {}, [], [], []
    for key in expected:
        row = seen.get(key, {})
        task = key[1]
        assessed_failure = row.get('correct') == 'false'
        required = ['started_at', 'ended_at',
                    'elapsed_seconds', 'visited_urls', 'author_help', 'correct',
                    'completed_without_help', 'is_non_author', 'assessor',
                    'manifest_before_path', 'manifest_after_path']
        required += ['blocked_reason'] if assessed_failure else ['answer', 'page_anchor', 'evidence_url']
        if task in protocol['base_tasks']:
            required += ['reading_ease_1_to_5', 'interest_1_to_5',
                         'naturalness_1_to_5', 'subjective_reason']
        elif task == 'S' and not assessed_failure:
            required += ['explanation_without_document', 'closed_document']
        elif task == 'R' and not assessed_failure:
            required += ['interruption_seconds', 'closed_document', 'resumed_from_start',
                         'pre_interrupt_note', 'resumed_state', 'next_action', 'next_branch',
                         'backtrack_urls']
        missing = [field for field in required if row.get(field) is None or not str(row.get(field, '')).strip()]
        # Missing assignments remain in the denominator, never counted as success.
        for field in ['author_help', 'correct', 'completed_without_help', 'is_non_author',
                      'closed_document', 'resumed_from_start', 'explanation_without_document']:
            if row.get(field, '') not in (None, '', 'true', 'false'):
                raise ValueError(f'Expected true/false for {field}: {key}')
        for field in ['elapsed_seconds', 'interruption_seconds']:
            if row.get(field, ''):
                try:
                    value = float(row[field])
                except ValueError as exc:
                    raise ValueError(f'Invalid {field}: {key}') from exc
                if not 0 <= value < float('inf'):
                    raise ValueError(f'Invalid {field}: {key}')
        for field, target in [('reading_ease_1_to_5', ease), ('interest_1_to_5', interest),
                              ('naturalness_1_to_5', naturalness)]:
            if row.get(field, ''):
                if row[field] not in ('1', '2', '3', '4', '5'):
                    raise ValueError(f'Invalid {field}: {key}')
                if task in protocol['base_tasks']:
                    target.append(int(row[field]))
        captures_valid = True
        for field in ['manifest_before_path', 'manifest_after_path']:
            capture = manifest_observations.get(row.get(field))
            if capture is None:
                captures_valid = False
                if row.get(field):
                    missing.append(field + '_unavailable')
            elif capture != (protocol['manifest_sha256'], protocol['build_id']):
                raise ValueError(f'Deployment changed before/after observation: {key}')
        if missing:
            pending.append({'participant_id': key[0], 'task_id': task, 'missing': missing})
        success = (not missing and row['is_non_author'] == 'true' and row['correct'] == 'true'
                   and row['completed_without_help'] == 'true' and row['author_help'] == 'false'
                   and captures_valid
                   and float(row['elapsed_seconds']) <= protocol['task_timeout_seconds'])
        if task == 'S':
            success = success and row.get('explanation_without_document') == 'true' and row.get('closed_document') == 'true'
        if task == 'R':
            success = (success and row.get('closed_document') == 'true'
                       and row.get('resumed_from_start') == 'true'
                       and float(row.get('interruption_seconds') or 0) >= protocol['interruption_seconds'])
        outcomes[key] = bool(success)

    base = [ok for (_, task), ok in outcomes.items() if task in protocol['base_tasks']]
    core = {task: all(ok for (_, t), ok in outcomes.items() if t == task) for task in ['S', 'R']}
    median = statistics.median(ease) if ease else None
    successful_distinct = {task for (_, task), ok in outcomes.items() if ok and task in protocol['base_tasks']}
    passed = (not pending and sum(base) >= protocol['minimum_base_successes']
              and len(successful_distinct) >= protocol['minimum_base_successes']
              and median is not None and median >= protocol['minimum_ease_median'] and all(core.values()))
    return {
        'schema': 1, 'source_kind': 'human', 'provenance': 'facilitator-declared; not independently authenticated',
        'status': 'pending' if pending else 'passed' if passed else 'needs-improvement',
        'build_id': protocol['build_id'], 'protocol_sha256': protocol_sha256,
        'assigned_base_tasks': len(base), 'unassisted_base_successes': sum(base),
        'distinct_base_tasks_succeeded': len(successful_distinct),
        'reading_ease_median': median, 'self_explanation_all': core['S'], 'resumption_all': core['R'],
        'transfer': [{'participant_id': p, 'success': ok} for (p, t), ok in outcomes.items() if t == 'X'],
        'subjective': {'interest': interest, 'naturalness': naturalness,
                       'note': 'Separate responses; no combined accuracy/experience score.'},
        'pending': pending, 'human_approval': 'unchanged', 'issue_completion': 'not-decided',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.protocol.read_bytes()
        protocol = json.loads(raw)
        hashes = {key: hashlib.sha256((args.protocol.parent / entry['path']).read_bytes()).hexdigest()
                  for key, entry in protocol['artifacts'].items()}
        with args.results.open(encoding='utf-8-sig', newline='') as source:
            rows = list(csv.DictReader(source))
        captures = {}
        for row in rows:
            for field in ['manifest_before_path', 'manifest_after_path']:
                path = row.get(field)
                if path and path not in captures:
                    try:
                        observed = (args.results.parent / path).read_bytes()
                    except OSError:
                        continue  # Unavailable observation remains pending in its assigned row.
                    captures[path] = hashlib.sha256(observed).hexdigest(), json.loads(observed)['build_id']
        result = summarize(protocol, rows, protocol_sha256=hashlib.sha256(raw).hexdigest(),
                           artifact_hashes=hashes, manifest_observations=captures)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
