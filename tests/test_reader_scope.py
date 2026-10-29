"""Fixed tasks precede output and candidate judgments; no real-person results."""
import copy

import pytest

from sdd.reader_scope import candidate, configuration_errors, report
from sdd.evidence import fingerprint
from sdd.design_reuse import topic_inputs


def scope():
    return {'revision': 1, 'change_reason': 'Initial fixed reader task.',
            'tasks': [{'id': 'adoption', 'goal': 'Find inputs and ownership.',
                       'completion': 'Reach both answer and its conditions.', 'requirements': ['inputs']}],
            'optional': [{'id': 'registers', 'location': 'detail.md#registers', 'reason': 'Hardware detail.'}],
            'excluded': [{'id': 'all-functions', 'reason': 'Not required for the adoption task.'}],
            'removed_requirements': []}


def section():
    return {'id': 'guide', 'reader_profile': 'vendor', 'reader_scope': scope(),
            'design_requirements': [{'id': 'inputs', 'question': 'What inputs?'}],
            'design_topics': [{'id': 'input-flow', 'covers': ['inputs']}]}


def decision(disposition='required'):
    return {'kind': 'add_topic', 'requirement': {'id': 'inputs'},
            'topic': {'sources': [{'id': 'condition'}]},
            'scope_decision': {'disposition': disposition, 'task': 'adoption',
                               'unmet_need': 'The required input exception is absent.',
                               'existing_topics': ['input-flow'], 'evidence': ['condition'], 'detail': ''}}


def test_missing_and_exception_remain_required_but_details_and_duplicates_do_not_grow_intro(sample_model):
    sec = section()
    assert not configuration_errors(sec)
    missing = report(sec, [{'id': 'inputs', 'status': 'missing', 'topics': []}], sample_model)
    assert missing['tasks'][0]['unresolved'] == ['inputs']
    assert missing['structural'] == 'incomplete'
    assert candidate(sec, decision())['disposition'] == 'required'
    for disposition in ('optional-detail', 'already-covered', 'out-of-scope', 'deferred'):
        data = decision(disposition)
        if disposition == 'optional-detail':
            data['scope_decision']['detail'] = 'detail.md#registers'
        with pytest.raises(ValueError, match='Only a required'):
            candidate(sec, data)
        data['kind'] = 'needs_review'
        data['scope_decision']['evidence'] = ['source-window']
        assert candidate(sec, data)['disposition'] == disposition


@pytest.mark.parametrize('field,value', [('task', 'invented'), ('evidence', []), ('existing_topics', ['invented'])])
def test_insufficient_or_unbound_candidate_is_not_completion(field, value):
    data = decision()
    data['scope_decision'][field] = value
    with pytest.raises(ValueError):
        candidate(section(), data)


def test_scope_change_invalidates_completion_and_topic_reuse(sample_model):
    sec = section()
    original = fingerprint(sample_model, sec)
    inputs = topic_inputs(sample_model, sec, 'fixed policy')
    changed = copy.deepcopy(sec)
    changed['reader_scope']['revision'] = 2
    changed['reader_scope']['change_reason'] = 'Owner must also find the exception.'
    changed['reader_scope']['tasks'][0]['completion'] += ' Explain the exception.'
    assert fingerprint(sample_model, changed) != original
    assert topic_inputs(sample_model, changed, 'fixed policy') != inputs
    assert topic_inputs(sample_model, sec, 'fixed policy') == inputs


def test_report_has_reachable_answers_selected_evidence_and_separate_review_states(sample_model):
    sample_model.evidence['guide/input-flow/source'] = {'text': 'fixed source'}
    sec = section()
    result = report(sec, [{'id': 'inputs', 'status': 'documented', 'topics': ['input-flow']}], sample_model)
    assert result['tasks'][0]['evidence'] == ['guide/input-flow/source']
    assert result['structural'] == 'linked'
    assert result['model_semantic'] == 'not-run' and result['human_task_test'] == 'pending'
    assert result['optional'] and result['excluded'] and result['unreviewed_scope']
    for _ in range(3):
        assert report(sec, [{'id': 'inputs', 'status': 'documented', 'topics': ['input-flow']}], sample_model) == result


def test_removing_questions_requires_explicit_revision_reason_and_removed_ids():
    import yaml
    from sdd.reader_scope import validate_change
    sec = section()
    prior = '---\n' + yaml.safe_dump({'generated_design': {'reader_scope': scope()}}) + '---\nBody'
    changed = copy.deepcopy(sec)
    changed['reader_scope']['tasks'][0]['requirements'] = ['new-question']
    with pytest.raises(ValueError, match='newer revision'):
        validate_change(prior, changed)
    changed['reader_scope'].update(revision=2, change_reason='Move old question to a detail guide.')
    with pytest.raises(ValueError, match='removed_requirements'):
        validate_change(prior, changed)
    changed['reader_scope']['removed_requirements'] = ['inputs']
    validate_change(prior, changed)
