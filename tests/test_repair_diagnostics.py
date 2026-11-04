"""Scripted regressions only: these tests do not make native CLI review claims."""
import copy
import json

import pytest

from sdd import generated_design
from sdd.generation_run import observe
from sdd.repair_diagnostics import ReviewAttempt, UnchangedRejectedReview
from sdd.visuals import VisualLabelConflict
from test_grounding_format_retry import unit_case, ScriptedAgent, request, counts, PASS, UNSUPPORTED
from test_generated_design import generated
from test_generated_visuals import automatic
from test_design_contracts import contract


@pytest.mark.parametrize('reformat', [False, True])
def test_identical_semantically_rejected_candidate_cannot_gain_a_lucky_pass(unit_case, reformat):
    unit_case[0].max_retries = 1
    raw = unit_case[-1]
    repeated = json.dumps(json.loads(raw), sort_keys=True) if reformat else raw
    agent = ScriptedAgent([('draft', raw), ('review', UNSUPPORTED), ('draft', repeated), ('review', PASS)])
    with observe(unit_case[0], 'scripted-repair-regression') as execution:
        with pytest.raises(generated_design._UnitRejected, match='원고·근거·판정 기준이 그대로'):
            request(unit_case, agent)
    assert counts(agent) == (2, 1)
    assert agent.replies == [('review', PASS)]
    rows = execution.report['repair_attempts']
    assert [r['category'] for r in rows] == ['semantic', 'verdict-conflict-risk']
    assert rows[1]['status'] == 'no-progress' and rows[1]['prior_finding_disposition'] == 'unjudged'
    assert rows[0]['next_action'] and rows[0]['details']['review_request_sha256']


def test_no_progress_skips_review_but_keeps_remaining_existing_draft_attempts(unit_case):
    raw = unit_case[-1]
    fixed = json.loads(raw)
    fixed['statements'][0]['text'] = '`stop()`은 `cancelPending()`을 호출해 대기 요청의 취소 처리를 시작합니다.'
    agent = ScriptedAgent([('draft', raw), ('review', UNSUPPORTED), ('draft', raw),
                           ('draft', json.dumps(fixed)), ('review', PASS)])
    with observe(unit_case[0], 'remaining-existing-budget') as execution:
        request(unit_case, agent)
    assert counts(agent) == (3, 2) and not agent.replies
    assert execution.report['repair_attempts'][1]['status'] == 'no-progress'
    assert execution.report['repair_attempts'][-1]['status'] == 'accepted-current-checks'


def test_unreadable_diagnostic_receipt_does_not_replace_original_result(unit_case):
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', PASS)])
    agent.last_receipt = unit_case[0].build_dir/'removed-receipt.json'
    with observe(unit_case[0], 'receipt-diagnostic') as execution:
        request(unit_case, agent)
    assert execution.report['repair_attempts'][0]['receipt']['status'] == 'unreadable'


def test_extra_diagnostic_write_failure_keeps_original_result(unit_case, monkeypatch):
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', PASS)])
    with observe(unit_case[0], 'diagnostic-write-failure') as execution:
        with monkeypatch.context() as patch:
            def fail_write():
                raise OSError('diagnostic write unavailable')
            patch.setattr(execution, 'persist', fail_write)
            with pytest.warns(RuntimeWarning, match='diagnostic journal write failed'):
                statements, _ = request(unit_case, agent)
            assert statements
        assert execution.report['repair_attempts'][0]['diagnostic_write_error']


@pytest.mark.parametrize('failure', [ValueError('agent failure'), TypeError('agent failure'), KeyError('agent failure'),
                                     RuntimeError('agent failure'), OSError('agent failure')])
def test_agent_exception_is_never_recorded_as_a_semantic_verdict(unit_case, failure):
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', failure), ('review', PASS)])
    with observe(unit_case[0], 'agent-failure') as execution:
        with pytest.raises(type(failure)) as raised:
            request(unit_case, agent)
    assert raised.value is failure
    assert counts(agent) == (1, 1) and agent.replies == [('review', PASS)]
    assert execution.report['repair_attempts'][0]['category'] == 'review-agent-failure'
    assert not execution.report['repair_attempts'][0].get('details', {}).get('review_request_sha256')


def test_checkpoint_failure_after_acceptance_is_not_a_semantic_rejection(unit_case, monkeypatch):
    from types import SimpleNamespace
    cfg = unit_case[0]
    cfg.raw.setdefault('review', {})['cli_checkpoint'] = True
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', PASS)])
    agent.unit = lambda *args, **kwargs: None
    failure = ValueError('checkpoint write failed')
    def write(*args):
        raise failure
    store = SimpleNamespace(path=cfg.build_dir/'cli-checkpoints/example.json', read=lambda: None, write=write)
    monkeypatch.setattr('sdd.design_checkpoint.store_for', lambda *args, **kwargs: (store, {}))
    with observe(cfg, 'checkpoint-failure') as execution:
        with pytest.raises(ValueError, match='checkpoint write failed') as raised:
            request(unit_case, agent)
    assert raised.value is failure and counts(agent) == (1, 1)
    assert not execution.report.get('repair_attempts')


def checkpoint_case(unit_case, monkeypatch):
    from types import SimpleNamespace
    cfg = unit_case[0]
    cfg.raw.setdefault('review', {})['cli_checkpoint'] = True
    saved = dict(identity={}, raw=unit_case[-1], receipts=[], statements=json.loads(unit_case[-1])['statements'])
    writes = []
    store = SimpleNamespace(path=cfg.build_dir/'cli-checkpoints/example.json', calls=cfg.build_dir/'prompts/calls',
        read=lambda: (saved, object()), write=lambda *args: writes.append(args))
    monkeypatch.setattr('sdd.design_checkpoint.store_for', lambda *args, **kwargs: (store, {}))
    monkeypatch.setattr('sdd.design_checkpoint.changes', lambda *args: (True, False))
    return saved, writes


def test_checkpoint_format_retry_keeps_the_receipted_draft(unit_case, monkeypatch):
    unit_case[0].max_retries = 0
    saved, writes = checkpoint_case(unit_case, monkeypatch)
    agent = ScriptedAgent([('review', 'not JSON'), ('review', PASS)])
    agent.unit = lambda *args, **kwargs: None
    statements, provenance = request(unit_case, agent)
    assert counts(agent) == (0, 2) and statements == saved['statements']
    assert provenance['revalidated'] and provenance['new_grounding_review']
    assert len(writes) == 1 and writes[0][0] == saved['raw']


def test_checkpoint_semantic_rejection_prevents_identical_lucky_review(unit_case, monkeypatch):
    unit_case[0].max_retries = 0
    saved, writes = checkpoint_case(unit_case, monkeypatch)
    agent = ScriptedAgent([('review', UNSUPPORTED), ('draft', unit_case[-1]), ('review', PASS)])
    agent.unit = lambda *args, **kwargs: None
    with observe(unit_case[0], 'checkpoint-semantic-rejection') as execution:
        with pytest.raises(generated_design._UnitRejected):
            request(unit_case, agent)
    assert counts(agent) == (1, 1) and not writes
    assert [r['category'] for r in execution.report['repair_attempts']] == ['semantic', 'verdict-conflict-risk']
    assert saved['raw'] == unit_case[-1]


def test_execution_limits_are_distinct_from_cli_and_semantic_failures():
    from sdd.generation_run import failure_kind
    from sdd.llm import AgentError
    assert failure_kind(AgentError('CLI 입력 한도를 초과했습니다.')) == 'cli-input-limit'
    assert failure_kind(AgentError('모델이 출력 토큰 한도에 도달했습니다.')) == 'model-output-limit'
    assert failure_kind(AgentError('CLI가 실패했습니다.')) == 'cli-failure'


@pytest.mark.parametrize('category,expected', [('review-format', 'review-format'),
    ('semantic', 'grounding-rejected'), ('verdict-conflict-risk', 'no-progress')])
def test_terminal_failure_retains_its_category_without_matching_model_wording(category, expected):
    from sdd.generation_run import failure_kind
    error = generated_design._UnitRejected('model reason happens to mention checkpoint', category=category)
    assert failure_kind(error) == expected


def test_rejected_candidate_is_remembered_across_operation_resume(unit_case):
    cfg = unit_case[0]
    cfg.raw['publication'] = dict(operation_id='scripted-resume')
    cfg.max_retries = 0
    first = ScriptedAgent([('draft', unit_case[-1]), ('review', UNSUPPORTED)])
    with observe(cfg, 'first') as previous:
        with pytest.raises(generated_design._UnitRejected):
            request(unit_case, first)
    original = previous.path.read_bytes()
    second = ScriptedAgent([('draft', unit_case[-1]), ('review', PASS)])
    with observe(cfg, 'resume'):
        with pytest.raises(generated_design._UnitRejected, match='원고·근거·판정 기준이 그대로'):
            request(unit_case, second)
    assert counts(second) == (1, 0)
    assert previous.path.read_bytes() == original


def test_writer_only_prompt_change_does_not_clear_the_same_rejected_review(unit_case):
    cfg = unit_case[0]
    cfg.raw['publication'] = dict(operation_id='scripted-writer-guidance-resume')
    cfg.max_retries = 0
    with observe(cfg, 'first'):
        with pytest.raises(generated_design._UnitRejected):
            request(unit_case, ScriptedAgent([('draft', unit_case[-1]), ('review', UNSUPPORTED)]))
    unit_case[3]['prompt'] = 'Writer guidance changed, but the same rejected candidate is returned.'
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', PASS)])
    with observe(cfg, 'resume'):
        with pytest.raises(generated_design._UnitRejected):
            request(unit_case, agent)
    assert counts(agent) == (1, 0)


@pytest.mark.parametrize('changed', ['condition', 'evidence', 'profile', 'criterion'])
def test_similar_claim_under_another_condition_is_not_an_identical_review(changed):
    class Agent:
        def chat(self, *args, **kwargs):
            return PASS
    payload = dict(statements=[dict(text='same words', condition='ready')], source_context='source A')
    profile = dict(model='approved-test-profile')
    first = ReviewAttempt(Agent(), {}, profile)
    first.chat('criterion', json.dumps(payload))
    rejected = {first.request: 'same problem, differently worded finding'}
    if changed == 'condition': payload['statements'][0]['condition'] = 'not ready'
    if changed == 'evidence': payload['source_context'] = 'source B'
    if changed == 'profile': profile = dict(model='another-approved-profile')
    second = ReviewAttempt(Agent(), rejected, profile)
    second.chat('changed criterion' if changed == 'criterion' else 'criterion', json.dumps(payload))
    assert second.request != first.request
    # This establishes a different review input, not resolution of the first finding.


def test_error_a_followed_by_b_is_not_automatically_counted_as_resolved(unit_case):
    raw = unit_case[-1]
    bad_source = json.loads(raw)
    bad_source['statements'][0]['quote'] = 'Not in the supplied source at all.'
    agent = ScriptedAgent([('draft', 'not JSON'), ('draft', json.dumps(bad_source)),
                           ('draft', raw), ('review', PASS)])
    with observe(unit_case[0], 'scripted-errors') as execution:
        request(unit_case, agent)
    rows = execution.report['repair_attempts']
    assert [r['category'] for r in rows[:2]] == ['format', 'deterministic-validation']
    assert rows[-1]['status'] == 'accepted-current-checks'
    assert all(r['prior_finding_disposition'] == 'unjudged' for r in rows[1:])
    assert not any('resolved' in r for r in rows)


def test_same_wording_is_not_enough_to_match_an_error_or_override_rejection():
    reviewer = ReviewAttempt(object(), {}, {})
    # A rejection is bound to the complete source/statement/criterion payload;
    # it cannot be cleared by an unbound textual assertion of resolution.
    payload = json.dumps(dict(statements=['claim'], source_context='source'))
    from sdd.repair_diagnostics import fingerprint
    key = fingerprint(dict(system='criterion', payload=json.loads(payload), profile={}, schema=None))
    reviewer.rejected[key] = 'Resolved, no modification necessary (unverified assertion).'
    with pytest.raises(UnchangedRejectedReview):
        reviewer.chat('criterion', payload)


def test_collision_reports_the_exact_pair_and_keeps_the_current_retry_budget(tmp_cfg, automatic):
    from sdd.generated_visuals import generate, materialize, plans
    section, model, _, base = automatic
    bad = copy.deepcopy(base.draft)
    bad['edges'][0].update(label=bad['nodes'][1]['label'], label_en='Another English translation')
    with pytest.raises(VisualLabelConflict) as error:
        materialize(tmp_cfg, model, section, plans(tmp_cfg, section)[0], bad, 'scripted')
    details = error.value.details
    assert details['first']['target'] == 'node:cancel'
    assert details['second']['target'] == 'edge:stop->cancel'
    assert details['first']['evidence'][0]['quote_sha256']
    assert 'Another English translation' in str(error.value)
    class Agent:
        def __init__(self): self.calls = []
        def chat(self, system, user, **options):
            self.calls.append(user)
            return json.dumps(bad if len(self.calls) == 1 else base.draft)
    agent = Agent()
    with observe(tmp_cfg, 'scripted-visual-repair') as execution:
        generate(tmp_cfg, model, section, agent)
    assert len(agent.calls) == 2
    assert 'node:cancel' in agent.calls[1] and 'edge:stop->cancel' in agent.calls[1]
    rows = execution.report['repair_attempts']
    assert rows[0]['category'] == 'format'
    assert rows[1]['prior_finding_disposition'] == 'unjudged'


@pytest.mark.parametrize('evidence', [['bad'], [{'quote': 3}]])
def test_malformed_evidence_is_not_an_attribute_error_from_diagnostics(tmp_cfg, automatic, evidence):
    from sdd.visuals import render_values
    section, model, _, _ = automatic
    graph = dict(id='malformed', topic='shutdown', kind='flow', title='Malformed evidence', question='Source?',
        nodes=[dict(id='a', label='label', label_en='label', evidence=evidence),
               dict(id='b', label='b', label_en='b', evidence=evidence)],
        edges=[dict(**{'from': 'a', 'to': 'b'}, label='edge', label_en='edge', evidence=evidence)])
    with pytest.raises(ValueError):
        render_values(tmp_cfg, model, section, [graph])


def test_terminal_visual_error_retains_the_failure_classification(tmp_cfg, automatic):
    from sdd.generated_visuals import generate
    from sdd.generation_run import failure_kind
    section, model, _, agent = automatic
    tmp_cfg.max_retries = 0
    agent.draft['edges'][0].update(label=agent.draft['nodes'][1]['label'], label_en='Different translation')
    with pytest.raises(ValueError) as error:
        generate(tmp_cfg, model, section, agent)
    assert failure_kind(error.value) == 'format'
