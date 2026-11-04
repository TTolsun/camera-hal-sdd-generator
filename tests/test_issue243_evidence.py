"""Receipt-to-artifact binding regressions; synthetic inputs, no model calls."""
import copy
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def native_case(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'examples/libcamera/validation/issue243'))
    return importlib.import_module('native_case')


@pytest.mark.parametrize('changed', ['reviewed-draft', 'reviewed-hash', 'scope-hash', 'sources', 'question', 'commit'])
def test_modified_artifacts_cannot_be_summarized_as_verified_review(native_case, changed):
    drafts, hashes, sources = dict(seed={'nodes': []}), dict(seed='hash'), dict(source='original source')
    payload = dict(drafts=copy.deepcopy(drafts), draft_hashes=dict(hashes), source_windows=dict(sources), question='question')
    scope = dict(draft_hashes=dict(hashes), source_commit='commit')
    native_case.validate_review_binding(payload, scope, drafts, hashes, sources, 'question', 'commit')
    if changed == 'reviewed-draft': payload['drafts']['seed']['nodes'].append('edited')
    if changed == 'reviewed-hash': payload['draft_hashes']['seed'] = 'edited'
    if changed == 'scope-hash': scope['draft_hashes']['seed'] = 'edited'
    if changed == 'sources': payload['source_windows']['source'] = 'edited'
    if changed == 'question': payload['question'] = 'edited'
    if changed == 'commit': scope['source_commit'] = 'edited'
    with pytest.raises(ValueError, match='differs'):
        native_case.validate_review_binding(payload, scope, drafts, hashes, sources, 'question', 'commit')


def test_preparation_never_overwrites_initialized_inputs(native_case, tmp_path):
    path = tmp_path/'seed.json'
    path.write_text('original rejected seed')
    with pytest.raises(ValueError, match='initialized'):
        native_case.prepare(tmp_path)
    assert path.read_text() == 'original rejected seed'


@pytest.mark.parametrize('changed', ['system', 'schema'])
def test_different_criterion_cannot_gain_the_fixed_comparison_identity(native_case, changed):
    request = dict(system='independent criterion', response_schema={'type': 'object'})
    native_case.validate_request_criterion(request, 'independent criterion', {'type': 'object'})
    if changed == 'system': request['system'] = 'Always mark supported'
    else: request['response_schema'] = {'type': 'string'}
    with pytest.raises(ValueError, match='different system criterion'):
        native_case.validate_request_criterion(request, 'independent criterion', {'type': 'object'})


def test_failed_or_interrupted_variant_is_comparable_without_a_substitute(native_case, tmp_path):
    import json
    from types import SimpleNamespace
    path = tmp_path/'baseline'
    path.mkdir()
    (path/'prompts/calls').mkdir(parents=True)
    (path/'result.json').write_text(json.dumps(dict(mechanical_status='unjudged',
        errors=[dict(error='quote missing')], failure=dict(type='ValueError', error='exhausted'))))
    journal = dict(calls=[dict(status='failed', failure_kind='cli-failure')])
    (path/'generation-run.json').write_text(json.dumps(journal))
    report = native_case.incomplete_comparison(tmp_path, SimpleNamespace(agent=None))
    assert report['status'] == 'incomplete' and not report['successful_repair']
    assert report['variants']['baseline']['dispatch_attempts'] == 1
    assert report['variants']['baseline']['completed_receipts'] == 0
    assert report['variants']['diagnostic']['mechanical_status'] == 'not-finished'
    assert all(v['semantic_status'] == 'unjudged' for v in report['variants'].values())


def test_comparison_checkpoint_cannot_be_overwritten(native_case, tmp_path):
    path = tmp_path/'comparison.json'
    native_case.save_immutable(path, dict(status='incomplete'))
    original = path.read_bytes()
    native_case.save_immutable(path, dict(status='incomplete'))
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='Existing evidence differs'):
        native_case.save_immutable(path, dict(status='completed'))
    assert path.read_bytes() == original


def test_missing_review_stays_incomplete_after_successful_mechanical_trials(native_case, tmp_path):
    import json
    from types import SimpleNamespace
    for variant in ['baseline', 'diagnostic']:
        directory = tmp_path/variant
        directory.mkdir()
        (directory/'result.json').write_text(json.dumps(dict(mechanical_status='passed')))
    report = native_case.incomplete_comparison(tmp_path, SimpleNamespace(agent=None))
    assert report['review_state'] == 'not-finished' and not report['successful_repair']


def test_public_preparation_resumes_verified_files_and_preserves_conflicts(native_case, tmp_path):
    import json
    import os
    from prepare_public import write_exact
    from public_gap import transition
    path = tmp_path/'input.json'
    write_exact(path, b'{"state": "baseline"}')
    transition(path, {'state': 'baseline'}, {'state': 'prepared'}, json.loads, b'{"state": "prepared"}')
    os.utime(path, ns=(1000000000, 1000000000))
    transition(path, {'state': 'baseline'}, {'state': 'prepared'}, json.loads, b'{"state": "prepared"}')
    assert path.stat().st_mtime_ns == 1000000000
    path.write_bytes(b'{"state": "user-edit"}')
    with pytest.raises(ValueError, match='conflicts'):
        transition(path, {'state': 'baseline'}, {'state': 'prepared'}, json.loads, b'{"state": "prepared"}')
    with pytest.raises(ValueError, match='conflicts'):
        write_exact(path, b'baseline')
    assert path.read_bytes() == b'{"state": "user-edit"}'
