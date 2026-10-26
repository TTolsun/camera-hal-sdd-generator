"""Only malformed grounding verdicts may retain the same live draft in memory."""
import json
from types import SimpleNamespace

import pytest

from sdd import generated_design, grounding
from sdd.config import AgentConfig
from sdd.generate import Generator
from test_generated_design import generated
from test_grounding_policy import (
    PREVIOUS_SHA, CLI_SCHEMA_SHA, _artifact, _design_agent, _edited_artifact,
    _previous_review, _review_result,
)


PASS = json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': 'Source matches.'}]})
UNSUPPORTED = json.dumps({'reviews': [{'index': 0, 'supported': False, 'reason': 'Unsupported claim.'}]})
OLD_CLI_SHA = '4720babc38b81fdd79472e63a8d122e720efe40e3abf50247be45197a122b3ea'


class ScriptedAgent:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, system, user, **options):
        self.calls.append((system, user, options))
        kind, reply = self.replies.pop(0)
        assert kind == ('review' if options['tag'].endswith('_grounding') else 'draft')
        assert options['response_schema']['required'] == ['reviews' if kind == 'review' else 'statements']
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def unit_case(tmp_cfg, generated):
    section, model, _, base = generated
    tmp_cfg.agent = AgentConfig(kind='cli', model='qwen3.5:9b-ctx64k',
        args=['--provider', 'custom', '--reasoning', 'high'], max_input_chars=18000)
    tmp_cfg.max_retries = 2
    raw = json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    return tmp_cfg, model, section, section['design_topics'][0], raw


def request(case, agent, *, archive=None):
    cfg, model, section, topic, _ = case
    return generated_design._request_unit(cfg, model, agent, section, topic,
        (None, 'Answer only from the source.', 'test-policy'), True, archive, {})


def counts(agent):
    reviews = sum(c[2]['tag'].endswith('_grounding') for c in agent.calls)
    return len(agent.calls) - reviews, reviews


@pytest.mark.parametrize('malformed', ['not JSON', '[]', '{"reviews":[]}',
    '{"type":"object","properties":{"reviews":{"type":"array"}}}',
    '{"reviews":[{"index":0,"supported":"true","reason":"Source matches."}]}'])
def test_malformed_review_keeps_one_live_draft_and_requests_new_review(unit_case, malformed):
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', raw), ('review', malformed), ('review', PASS)])
    statements, replayed = request(unit_case, agent)
    assert statements == json.loads(raw)['statements'] and replayed is None
    assert counts(agent) == (1, 2) and not agent.replies
    assert agent.calls[1][:2] == agent.calls[2][:2]
    assert agent.calls[1][2]['response_schema'] == agent.calls[2][2]['response_schema']
    assert agent.calls[1][2]['tag'] != agent.calls[2][2]['tag']


def test_semantic_rejection_requires_a_new_draft(unit_case):
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', raw), ('review', UNSUPPORTED), ('draft', raw), ('review', PASS)])
    request(unit_case, agent)
    assert counts(agent) == (2, 2)
    assert 'Unsupported claim.' in agent.calls[2][1]


def test_format_then_semantic_rejection_clears_the_pending_draft(unit_case):
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', raw), ('review', 'not JSON'), ('review', UNSUPPORTED),
                           ('draft', raw), ('review', PASS)])
    request(unit_case, agent)
    assert counts(agent) == (2, 3)
    assert 'Unsupported claim.' in agent.calls[3][1]


def test_invalid_draft_is_never_retained_for_review(unit_case):
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', 'not JSON'), ('draft', raw), ('review', PASS)])
    request(unit_case, agent)
    assert counts(agent) == (2, 1)


@pytest.mark.parametrize('retries', [0, 1, 2])
def test_format_exhaustion_consumes_only_the_existing_outer_budget(unit_case, retries):
    unit_case[0].max_retries = retries
    agent = ScriptedAgent([('draft', unit_case[-1]), *[('review', 'not JSON')] * (retries + 1)])
    with pytest.raises(generated_design._UnitRejected, match='LLM 답변 검증 실패'):
        request(unit_case, agent)
    assert counts(agent) == (1, retries + 1) and not agent.replies


@pytest.mark.parametrize('location', ['draft', 'review'])
@pytest.mark.parametrize('message', ['CLI timeout', 'CLI nonzero exit'])
def test_cli_failure_propagates_without_retry_or_substitution(unit_case, location, message):
    failure = RuntimeError(message)
    replies = [('draft', unit_case[-1])] if location == 'review' else []
    agent = ScriptedAgent([*replies, (location, failure)])
    with pytest.raises(RuntimeError) as raised:
        request(unit_case, agent)
    assert raised.value is failure
    assert counts(agent) == ((1, 1) if location == 'review' else (1, 0))


def test_pending_draft_is_structurally_revalidated_before_the_next_review(unit_case):
    cfg, model, _, _, raw = unit_case
    agent = ScriptedAgent([('draft', raw), ('review', 'not JSON'), ('draft', 'not JSON')])
    original = agent.chat
    def chat(system, user, **options):
        result = original(system, user, **options)
        if options['tag'].endswith('_grounding'):
            # Simulate changed source input between two attempts. The old
            # quote must fail before another grounding call can be made.
            model.evidence['device/stop/stop']['text'] = 'void changed() { return; }'
        return result
    agent.chat = chat
    with pytest.raises(ValueError, match='LLM 답변 검증 실패'):
        request(unit_case, agent)
    assert counts(agent) == (2, 1) and not agent.replies


def test_candidate_does_not_survive_across_units(unit_case):
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', raw), ('review', 'not JSON'), ('review', PASS),
                           ('draft', raw), ('review', PASS)])
    request(unit_case, agent)
    request(unit_case, agent)
    assert counts(agent) == (2, 3)


def test_a_cached_draft_does_not_gain_the_live_format_retry_path(unit_case, monkeypatch):
    from sdd import answer_cache
    raw = unit_case[-1]
    monkeypatch.setattr(answer_cache, 'read', lambda path: raw)
    agent = ScriptedAgent([('review', 'not JSON'), ('draft', raw), ('review', PASS)])
    request(unit_case, agent)
    assert counts(agent) == (1, 2) and not agent.replies


def test_budget_change_stops_before_another_review(unit_case):
    agent = ScriptedAgent([('draft', unit_case[-1]), ('review', 'not JSON')])
    original = agent.chat
    def chat(system, user, **options):
        result = original(system, user, **options)
        if options['tag'].endswith('_grounding'):
            unit_case[0].agent.max_input_chars = 1
        return result
    agent.chat = chat
    with pytest.raises(ValueError, match='예산을 초과') as rejected:
        request(unit_case, agent)
    assert type(rejected.value) is ValueError
    assert counts(agent) == (1, 1)


def test_format_retry_does_not_repeat_optional_prose_revision(unit_case):
    unit_case[0].raw.setdefault('review', {})['design_revision'] = True
    raw = unit_case[-1]
    agent = ScriptedAgent([('draft', raw), ('draft', raw), ('review', 'not JSON'), ('review', PASS)])
    request(unit_case, agent)
    assert counts(agent) == (2, 2)
    assert agent.calls[1][2]['tag'].endswith('_revision')


@pytest.mark.parametrize('raw', ['not JSON', '[]', '{}', '{"reviews":[]}',
    '{"reviews":[{"index":true,"supported":true,"reason":"ok"}]}',
    '{"reviews":[{"index":0,"supported":true,"reason":" "}]}',
    json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': 'x' * 401}]}),
    '{"reviews":[{"index":0,"supported":true,"reason":"ok","extra":1}]}'])
def test_only_malformed_review_responses_have_the_explicit_format_type(raw):
    agent = SimpleNamespace(chat=lambda *a, **kw: raw)
    generator = SimpleNamespace(cfg=SimpleNamespace(agent=AgentConfig(kind='cli', max_input_chars=10000)), agent=agent)
    statement = dict(text='반환합니다.', quote='return value;', evidence=['source'])
    with pytest.raises(grounding.GroundingFormatError) as rejected:
        grounding.review(generator, {'question': '반환값은 무엇입니까?'}, [statement], {'source': 'return value;'}, 'test')
    assert type(rejected.value) is grounding.GroundingFormatError
    assert isinstance(rejected.value, ValueError)


@pytest.mark.parametrize('reason', ['x', 'x' * 400])
def test_reason_bounds_and_false_verdict_semantics_are_unchanged(reason):
    raw = json.dumps({'reviews': [{'index': 0, 'supported': False, 'reason': reason}]})
    generator = SimpleNamespace(cfg=SimpleNamespace(agent=AgentConfig(kind='cli', max_input_chars=10000)),
                                agent=SimpleNamespace(chat=lambda *a, **kw: raw))
    with pytest.raises(ValueError) as rejected:
        grounding.review(generator, {'question': '반환값은 무엇입니까?'},
            [dict(text='반환합니다.', quote='return value;', evidence=['source'])], {'source': 'return value;'}, 'test')
    assert type(rejected.value) is ValueError
    assert str(rejected.value) == '모델 근거 대조 실패 (승인 아님): paragraph 1: ' + reason


@pytest.mark.parametrize('kind', ['ollama', 'openai-compatible'])
def test_frozen_http_invalid_json_keeps_request_and_error_text(kind):
    before = _review_result(_previous_review(), kind, 'not JSON')
    after = _review_result(grounding.review, kind, 'not JSON')
    assert before[0] == after[0] and before[2] == after[2]
    assert before[1] == 'JSONDecodeError' and after[1] == 'GroundingFormatError'


def test_only_the_exact_current_hash_aliases_to_the_original_http_policy():
    assert grounding.policy_hash() == CLI_SCHEMA_SHA
    assert generated_design._HTTP_GROUNDING_SCHEMA_COMPATIBILITY == {CLI_SCHEMA_SHA: PREVIOUS_SHA}
    assert generated_design._http_grounding_policy(OLD_CLI_SHA) == OLD_CLI_SHA
    assert generated_design._http_grounding_policy('f' * 64) == 'f' * 64


@pytest.mark.parametrize('kind', ['cli', 'ollama', 'openai-compatible'])
def test_the_previous_cli_policy_is_not_a_legacy_http_alias(tmp_cfg, generated, kind):
    section, model, _, base = generated
    tmp_cfg.agent.kind, tmp_cfg.agent.model = kind, 'test-model'
    tmp_cfg.raw.setdefault('review', {})['design_grounding'] = True
    text = Generator(tmp_cfg, model, _design_agent(base)).run()[0].read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='정책'):
        generated_design.verify(model, section, _edited_artifact(text, grounding_policy=OLD_CLI_SHA))
    expected = CLI_SCHEMA_SHA if kind == 'cli' else PREVIOUS_SHA
    assert _artifact(text)['grounding_policy'] == expected
