import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from sdd.reader_study import summarize


@pytest.fixture
def study():
    protocol = dict(build_id='frozen', manifest_sha256='manifest-hash', base_tasks=['a0', 'b0', 'a1', 'b1', 'a2', 'b2'],
                    participants=[dict(id=f'P{i}', perspective=role, tasks=[f'a{i}', f'b{i}', 'S', 'R', 'X'])
                                  for i, role in enumerate(['new_developer', 'other_team', 'non_author'])],
                    minimum_base_successes=5, minimum_ease_median=4,
                    task_timeout_seconds=600, interruption_seconds=300,
                    artifacts={key: dict(path=key, sha256='frozen-artifact') for key in
                               ['instructions', 'participant', 'rubric', 'baseline', 'legacy_rubric']})
    rows = []
    for participant in protocol['participants']:
        for task in participant['tasks']:
            rows.append(dict(participant_id=participant['id'], perspective=participant['perspective'], task_id=task,
                             build_id='frozen', protocol_sha256='hash', source_kind='human',
                             answer='Recorded answer', page_anchor='page#answer', evidence_url='page#evidence',
                             started_at='observed start', ended_at='observed end', elapsed_seconds='50',
                             visited_urls='page', backtrack_urls='none', author_help='false', correct='true',
                             completed_without_help='true', is_non_author='true', assessor='assessor',
                             reading_ease_1_to_5='4', interest_1_to_5='2', naturalness_1_to_5='3',
                             subjective_reason='Actual comment', explanation_without_document='true',
                             closed_document='true', resumed_from_start='true', interruption_seconds='300',
                             pre_interrupt_note='note', resumed_state='state', next_action='inspect', next_branch='branch'))
            rows[-1].update(manifest_before_path='before.json', manifest_after_path='after.json')
    return protocol, rows


def report(study):
    return summarize(*study, protocol_sha256='hash', artifact_hashes={key: 'frozen-artifact' for key in study[0]['artifacts']},
                     manifest_observations={name: ('manifest-hash','frozen') for name in ['before.json','after.json']})


def test_completed_study_keeps_experience_separate_and_never_closes_issue(study):
    result = report(study)
    assert result['status'] == 'passed'
    assert result['assigned_base_tasks'] == 6
    assert result['subjective']['interest'] == [2] * 6
    assert result['issue_completion'] == 'not-decided'
    assert result['human_approval'] == 'unchanged'


def test_empty_missing_and_helped_tasks_stay_in_denominator(study):
    protocol, rows = study
    empty = report((protocol, []))
    assert empty['status'] == 'pending' and empty['assigned_base_tasks'] == 6
    rows.pop(0)
    rows[0]['author_help'] = 'true'
    result = report(study)
    assert result['status'] == 'pending' and result['unassisted_base_successes'] == 4


@pytest.mark.parametrize('field,value', [('source_kind', 'agent'), ('build_id', 'other'),
                                        ('protocol_sha256', 'old'), ('perspective', 'other_team'),
                                        ('correct', 'yes'), ('elapsed_seconds', 'nan'),
                                        ('reading_ease_1_to_5', '6')])
def test_provenance_mixing_and_invalid_observations_are_rejected(study, field, value):
    study[1][0][field] = value
    with pytest.raises(ValueError):
        report(study)


def test_duplicate_or_unassigned_response_is_rejected(study):
    study[1].append(copy.deepcopy(study[1][0]))
    with pytest.raises(ValueError):
        report(study)


@pytest.mark.parametrize('task,field,value', [('S', 'closed_document', 'false'),
                                           ('R', 'interruption_seconds', '299'),
                                           ('R', 'resumed_from_start', 'false'),
                                           ('R', 'next_branch', '')])
def test_every_participant_must_explain_and_resume(study, task, field, value):
    next(row for row in study[1] if row['task_id'] == task)[field] = value
    result = report(study)
    assert result['status'] != 'passed'


def test_transfer_does_not_inflate_base_success(study):
    for row in study[1]:
        if row['task_id'].startswith('a'):
            row['correct'] = 'false'
            row['blocked_reason'] = 'Recorded wrong answer.'
    result = report(study)
    assert result['status'] == 'needs-improvement'
    assert result['unassisted_base_successes'] == 3


@pytest.mark.parametrize('change', ['omit-core', 'duplicate-person', 'lower-threshold', 'lose-perspective', 'omit-base'])
def test_protocol_cannot_weaken_precommitted_design(study, change):
    protocol = study[0]
    if change == 'omit-core':
        protocol['participants'][0]['tasks'].remove('S')
    elif change == 'duplicate-person':
        protocol['participants'][1]['id'] = protocol['participants'][0]['id']
    elif change == 'lower-threshold':
        protocol['minimum_base_successes'] = 1
    elif change == 'lose-perspective':
        protocol['participants'][0]['perspective'] = 'non_author'
    else:
        protocol['participants'][0]['tasks'].remove('a0')
    with pytest.raises(ValueError):
        report(study)


def test_changed_rubric_cannot_reuse_prior_result_fingerprint(study):
    with pytest.raises(ValueError, match='Frozen'):
        summarize(*study, protocol_sha256='hash', artifact_hashes={}, manifest_observations={})


def test_truncated_csv_and_missing_capture_cannot_pass(study):
    study[1][0]['answer'] = None
    assert report(study)['status'] == 'pending'
    study[1][0]['answer'] = 'answer'
    study[1][0]['manifest_before_path'] = ''
    assert report(study)['status'] == 'pending'
    study[1][0]['correct'] = None
    assert report(study)['assigned_base_tasks'] == 6
    study[1][0]['manifest_before_path'] = 'missing.json'
    assert report(study)['status'] == 'pending'


def test_observed_changed_deployment_is_rejected(study):
    with pytest.raises(ValueError, match='Deployment changed'):
        summarize(*study, protocol_sha256='hash', artifact_hashes={key:'frozen-artifact' for key in study[0]['artifacts']},
                  manifest_observations={'before.json': ('changed','other')})


def test_recorded_failure_without_found_answer_still_allows_five_of_six(study):
    study[1][0].update(correct='false', completed_without_help='false', answer='',
                        page_anchor='', evidence_url='', blocked_reason='Could not locate the evidence.')
    result = report(study)
    assert result['status'] == 'passed'
    assert result['unassisted_base_successes'] == 5
    assert result['assigned_base_tasks'] == 6


def test_additional_participant_repeats_fixed_tasks_without_dropping_assignments(study):
    protocol, rows = study
    participant = copy.deepcopy(protocol['participants'][0])
    participant['id'] = 'P4'
    protocol['participants'].append(participant)
    extra = [dict(row, participant_id='P4') for row in rows[:5]]
    rows.extend(extra)
    result = report(study)
    assert result['status'] == 'passed' and result['assigned_base_tasks'] == 8


def test_repeated_success_cannot_cover_failure_of_other_fixed_questions(study):
    protocol, rows = study
    for row in rows:
        if row['task_id'] in ['a1','b1','a2','b2']:
            row.update(correct='false',blocked_reason='Could not answer.')
    for i in range(4,7):
        participant = dict(protocol['participants'][0], id=f'P{i}')
        protocol['participants'].append(participant)
        rows.extend(dict(row, participant_id=f'P{i}') for row in rows[:5])
    result = report(study)
    assert result['unassisted_base_successes'] == 8
    assert result['distinct_base_tasks_succeeded'] == 2
    assert result['status'] == 'needs-improvement'


def test_published_blank_packet_has_valid_fingerprints_and_no_human_results():
    packet=Path(__file__).parents[1]/'docs/libcamera/records/issue-248'
    raw=(packet/'protocol.json').read_bytes()
    protocol=json.loads(raw)
    hashes={key:hashlib.sha256((packet/entry['path']).read_bytes()).hexdigest()
            for key,entry in protocol['artifacts'].items()}
    with (packet/'human-results.csv').open(encoding='utf-8',newline='') as source:
        rows=list(csv.DictReader(source))
    assert len(rows)==15 and all(not row['answer'] for row in rows)
    result=summarize(protocol,rows,protocol_sha256=hashlib.sha256(raw).hexdigest(),
                     artifact_hashes=hashes,manifest_observations={})
    assert result['status']=='pending' and result['unassisted_base_successes']==0
