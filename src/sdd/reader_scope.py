"""Optional reader tasks bound to existing design requirements and review records."""
from __future__ import annotations

import copy
import re

from jsonschema import Draft202012Validator

TEXT = {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
IDS = {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': TEXT}


def obj(properties, required=None):
    return {'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': list(properties) if required is None else required}


SCHEMA = obj({
    'revision': {'type': 'integer', 'minimum': 1}, 'change_reason': TEXT,
    'tasks': {'type': 'array', 'minItems': 1, 'items': obj({
        'id': TEXT, 'goal': TEXT, 'completion': TEXT, 'requirements': IDS})},
    'optional': {'type': 'array', 'items': obj({'id': TEXT, 'location': TEXT, 'reason': TEXT})},
    'excluded': {'type': 'array', 'items': obj({'id': TEXT, 'reason': TEXT})},
    'removed_requirements': {'type': 'array', 'uniqueItems': True, 'items': TEXT},
})


def configuration_errors(section):
    scope = section.get('reader_scope')
    if scope is None:
        return []
    errors = [f'reader_scope/{"/".join(map(str, e.path))}: {e.message}'
              for e in Draft202012Validator(SCHEMA).iter_errors(scope)]
    if errors:
        return errors
    if not section.get('reader_profile') or not section.get('design_requirements'):
        errors.append('reader_scope requires an existing reader_profile and design_requirements.')
    required = {r['id'] for r in section.get('design_requirements', [])}
    covered = {rid for task in scope['tasks'] for rid in task['requirements']}
    if required != covered:
        errors.append('reader_scope tasks must reference every current requirement, without unknown IDs.')
    all_ids = [v['id'] for field in ('tasks', 'optional', 'excluded') for v in scope[field]]
    if len(all_ids) != len(set(all_ids)):
        errors.append('reader_scope task/detail/exclusion IDs must be unique.')
    if required & set(scope['removed_requirements']):
        errors.append('Removed requirements cannot still be current requirements.')
    return errors


def report(section, requirements, model):
    """Structural answer reachability; semantic judgment and people stay separate."""
    scope = section.get('reader_scope')
    if scope is None:
        return None
    by_id = {r['id']: r for r in requirements}
    tasks = []
    for task in scope['tasks']:
        answers = [by_id[rid] for rid in task['requirements'] if rid in by_id]
        topics = sorted({tid for answer in answers for tid in answer['topics']})
        missing = [rid for rid in task['requirements']
                   if by_id.get(rid, {}).get('status') != 'documented']
        tasks.append({**task, 'status': 'missing' if missing else 'structurally-linked',
                      'unresolved': missing, 'topics': topics,
                      'evidence': sorted(k for k in model.evidence
                          if any(k.startswith(f"{section['id']}/{tid}/") for tid in topics))})
    return {**copy.deepcopy(scope), 'reader': section.get('reader_profile'), 'tasks': tasks,
            'structural': 'incomplete' if any(t['unresolved'] for t in tasks) else 'linked',
            'model_semantic': 'not-run', 'human_task_test': 'pending',
            'reviewed_scope': 'Configured required answers and their selected excerpts only.',
            'unreviewed_scope': 'Other source windows, product operation and real reader task performance.'}


DECISIONS = {'required', 'optional-detail', 'already-covered', 'out-of-scope', 'deferred'}


def candidate(section, data):
    """A model's relevance judgment is explicit; IDs are mechanically checked."""
    scope = section.get('reader_scope')
    if scope is None:
        return None
    assessment = data.get('scope_decision')
    schema = obj({'disposition': {'enum': sorted(DECISIONS)}, 'task': TEXT,
                  'unmet_need': TEXT, 'existing_topics': {'type': 'array', 'uniqueItems': True, 'items': TEXT},
                  'evidence': IDS, 'detail': {'type': 'string'}})
    errors = list(Draft202012Validator(schema).iter_errors(assessment))
    if errors:
        raise ValueError('Reader scope decision is missing or invalid: ' + errors[0].message)
    tasks = {t['id']: t for t in scope['tasks']}
    if assessment['task'] not in tasks:
        raise ValueError('Scope decision must identify an existing reader task.')
    topics = {t['id'] for t in section.get('design_topics', [])}
    if not set(assessment['existing_topics']) <= topics:
        raise ValueError('Scope decision refers to unknown existing topics.')
    if assessment['disposition'] == 'already-covered' and not assessment['existing_topics']:
        raise ValueError('Already-covered requires an existing answer location.')
    if assessment['disposition'] == 'already-covered':
        required = set(tasks[assessment['task']]['requirements'])
        covered = {rid for topic in section.get('design_topics', [])
                   if topic['id'] in assessment['existing_topics']
                   for rid in topic.get('covers', [])}
        if not required & covered:
            raise ValueError('Existing answer location does not cover the selected task.')
    if data.get('kind') == 'no_gap' and assessment['disposition'] not in {'already-covered', 'out-of-scope'}:
        raise ValueError('no_gap cannot mark an unmet or deferred task complete.')
    if assessment['disposition'] == 'optional-detail' and assessment['detail'] not in {
            d['location'] for d in scope['optional']}:
        raise ValueError('Optional detail must use a declared detail location.')
    if data.get('kind') == 'add_topic':
        requirement, topic = data.get('requirement'), data.get('topic')
        if not isinstance(requirement, dict) or not isinstance(topic, dict) or not isinstance(topic.get('sources'), list):
            raise ValueError('Reader candidate needs a requirement, topic and source list.')
        if assessment['disposition'] != 'required':
            raise ValueError('Only a required unmet reader task can add overview prose.')
        if requirement.get('id') not in tasks[assessment['task']]['requirements']:
            raise ValueError('New prose must answer an existing required task question.')
        if any(not isinstance(source, dict) or not isinstance(source.get('id'), str) for source in topic['sources']):
            raise ValueError('Reader candidate sources need string IDs.')
        source_ids = {s['id'] for s in topic['sources']}
        if not set(assessment['evidence']) <= source_ids:
            raise ValueError('Reader decision evidence must be supplied by this candidate.')
    elif not set(assessment['evidence']) <= {'source-window', *[
            s['id'] for topic in section.get('design_topics', []) for s in topic.get('sources', [])]}:
        raise ValueError('Decision evidence must reference the supplied window or known sources.')
    return assessment


def validate_locations(sections):
    from .config import section_output
    outputs = {section_output(s) for s in sections}
    for section in sections:
        if not section.get('reader_scope'):
            continue
        errors = configuration_errors(section)
        if errors:
            raise ValueError(' / '.join(errors))
        for detail in section['reader_scope']['optional']:
            if detail['location'].split('#', 1)[0] not in outputs:
                raise ValueError('Reader optional detail must link to a configured page.')
    return sections


def validate_change(previous, section):
    """Scope removals/edits require an explicit new revision and removal reason."""
    if not previous:
        return
    from .document_metadata import split_frontmatter
    metadata, _ = split_frontmatter(previous)
    old = metadata.get('generated_design', {}).get('reader_scope')
    current = section.get('reader_scope')
    if old is None or old == current:
        return
    if current is None:
        raise ValueError('Removing reader_scope requires an explicit lifecycle/scope migration, not silent regeneration.')
    if current['revision'] <= old['revision'] or current['change_reason'] == old['change_reason']:
        raise ValueError('Changed reader scope requires a newer revision and a new change_reason.')
    prior = {rid for task in old['tasks'] for rid in task['requirements']}
    now = {rid for task in current['tasks'] for rid in task['requirements']}
    if not prior - now <= set(current['removed_requirements']):
        raise ValueError('Removed scope questions must be listed in removed_requirements with the change reason.')


def preserve_unchanged(previous, candidate):
    """Keep a validated manuscript when only per-run diagnostics/time differ.

    Actual reuse counts remain in generation-runs. All inputs, answers, policies,
    source revision, display content and review state still have to match.
    """
    from .document_metadata import split_frontmatter

    def normalized(text):
        meta, body = split_frontmatter(text)
        meta.pop('generated_at', None)
        artifact = meta.get('generated_design', {})
        for key in ('reused_topics', 'generated_topics', 'replayed_units', 'body_sha256', 'reuse_lineage'):
            artifact.pop(key, None)
        body = re.sub(r'(?m)^(    - 검토 상태 기록일: )\d{4}-\d{2}-\d{2}', r'\1DATE', body)
        return meta, body
    return normalized(previous) == normalized(candidate)
