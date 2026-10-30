"""Single and batch envelopes share the same string validation policy."""

import copy
import json

import pytest

from sdd.llm import SCHEMA_KINDS
from sdd.translation import translate_missing


@pytest.mark.parametrize('source,text,valid', [
    ('설명', '  Description.  ', True),
    ('설명', '', False),
    ('설명', ' \n\t ', False),
    ('설명', None, False),
    ('설명', 17, False),
    ('설명', 'Description 설명', False),
    ('설명', '{"text": "Description."}', False),
    ('설명', ' \n{"texts": ["Description."]}\n ', False),
    ('설명', '{"translation": "Description."}', False),
    ('설명', '{"translations": {"0": "Description."}}', False),
    ('설명', '[{"text": "Description."}]', False),
    ('설명', '[[{"translations": ["Description."]}]]', False),
    ('JSON 예제', '{"format": "RGB888", "size": [640, 480]}', True),
    ('JSON 예제', '[{"format": "NV12"}, {"format": "RGB888"}]', True),
    ('JSON 예제', '{"type": "caption", "text": "Camera"}', True),
    ('JSON 예제', '["RGB888", "NV12"]', True),
    ('JSON 예제', 'The response contains {"text": "Camera"}.', True),
    ('JSON 코드', '```json\n{"text": "Camera"}\n```', True),
    ('{{0}} 처리', '{{0}} processes.', True),
    ('{{0}} 처리', 'Processes.', False),
    ('{{0}} 처리', '{{0}} processes {{0}}.', False),
    ('{{0}} 처리', '{{1}} processes.', False),
    ('{{0}} 처리', '{{0}} processes {{1}}.', False),
    ('{{0}}에 {{0}}을 적용합니다.', 'Apply {{0}} to {{0}}.', True),
    ('{{0}}에 {{0}}을 적용합니다.', 'Apply {{0}}.', False),
    ('호출자는 {{0}}을 유지해야 합니다.', 'The caller must retain {{0}}.', True),
    ('호출자는 {{0}}을 유지해야 합니다.', 'The caller shall retain {{0}}.', True),
    ('호출자는 {{0}}을 유지해야 합니다.', 'The caller should retain {{0}}.', False),
    ('호출자는 {{0}}을 유지해야 합니다.', 'The caller may retain {{0}}.', False),
    ('호출자는 {{0}}을 해제해서는 안 됩니다.', 'The caller must not release {{0}}.', True),
    ('호출자는 {{0}}을 해제해서는 안 됩니다.', 'The caller should not release {{0}}.', False),
    ('{{0}} 주석은 타이밍 정보를 문서화해야 함을 요청합니다.',
     'The {{0}} comment requests that timing information be documented.', True),
])
def test_single_and_batch_make_identical_string_decisions(tmp_cfg, source, text, valid):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.max_retries = 0
    catalog = {'strings': {'기존 문장': 'Existing.', source: ''}}
    original = copy.deepcopy(catalog)
    for size in (1, 4):
        tmp_cfg.raw['site'] = {'translation_batch_size': size}
        class Agent:
            def chat(self, system, user, **kwargs):
                data = json.loads(user)
                if size == 1:
                    assert data['source'] == source
                    return json.dumps({'text': text})
                return json.dumps({'translations': {key: text for key in data['texts']}})
        if valid:
            translated = translate_missing(tmp_cfg, catalog, Agent())
            assert translated['strings'][source] == text.strip()
            assert translated['strings']['기존 문장'] == 'Existing.'
        else:
            with pytest.raises(ValueError, match='failed validation'):
                translate_missing(tmp_cfg, catalog, Agent())
        assert catalog == original


@pytest.mark.parametrize('kind', [*SCHEMA_KINDS, 'openai-compatible'])
@pytest.mark.parametrize('size', [1, 4])
def test_schema_transport_policy_includes_cli_for_both_envelopes(tmp_cfg, kind, size):
    tmp_cfg.agent.kind = kind
    tmp_cfg.raw['site'] = {'translation_batch_size': size}
    class Agent:
        def chat(self, system, user, **kwargs):
            if kind in SCHEMA_KINDS:
                schema = kwargs['response_schema']
                assert schema['required'] == ['text' if size == 1 else 'translations']
                assert schema['additionalProperties'] is False
                if size > 1:
                    assert schema['properties']['translations']['required'] == ['0']
            else:
                assert 'response_schema' not in kwargs
            return json.dumps({'text': 'Description.'} if size == 1 else
                              {'translations': {'0': 'Description.'}})
    assert translate_missing(tmp_cfg, {'strings': {'설명': ''}}, Agent())['strings']['설명'] == 'Description.'


@pytest.mark.parametrize('response', [
    {'translations': {'0': '{{1}} processes.', '1': '{{0}} returns.'}},
    {'translations': {'0': '{{0}} processes.', '1': 'Returns.'}},
    {'translations': {'0': '{{0}} processes.', '1': '{{1}} returns {{1}}.'}},
    {'translations': {'0': '{{0}} processes.'}},
    {'translations': {'0': '{{0}} processes.', '1': '{{1}} returns.', 'extra': 'Extra.'}},
    {'translations': {}},
    {'translations': {'0': '{{0}} processes.', '1': '{{1}} returns.'}, 'extra': True},
])
def test_batch_rejects_moved_placeholders_and_missing_extra_ids(tmp_cfg, response):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.max_retries = 0
    tmp_cfg.raw['site'] = {'translation_batch_size': 4}
    catalog = {'strings': {'{{0}} 처리': '', '{{1}} 반환': ''}, 'review_status': 'original'}
    original = copy.deepcopy(catalog)
    class Agent:
        def chat(self, *args, **kwargs):
            return json.dumps(response)
    with pytest.raises(ValueError, match='batch failed validation'):
        translate_missing(tmp_cfg, catalog, Agent())
    assert catalog == original


@pytest.mark.parametrize('size', [1, 4])
def test_nested_response_wrapper_retries_only_the_invalid_display_text(tmp_cfg, size):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.raw['site'] = {'translation_batch_size': size}
    source = '{{0}} 설명'

    class Agent:
        calls = 0

        def chat(self, system, user, **kwargs):
            self.calls += 1
            request = json.JSONDecoder().raw_decode(user)[0]
            if self.calls == 2:
                assert 'JSON response wrapper' in user
            text = '{"text": "{{0}} description."}' if self.calls == 1 else '{{0}} description.'
            if size == 1:
                assert request['source'] == source
                return json.dumps({'text': text})
            if self.calls == 1:
                return json.dumps({'translations': {'0': 'Existing description.', '1': text}})
            assert request['texts'] == {'1': source}
            return json.dumps({'translations': {'1': text}})

    agent = Agent()
    catalog = {'strings': {source: ''}} if size == 1 else {'strings': {'첫 설명': '', source: ''}}
    result = translate_missing(tmp_cfg, catalog, agent)
    assert agent.calls == 2
    assert result['strings'][source] == '{{0}} description.'
    if size > 1:
        assert result['strings']['첫 설명'] == 'Existing description.'


@pytest.mark.parametrize('size', [1, 4])
@pytest.mark.parametrize('cli_fails', [False, True])
def test_legacy_response_wrapper_is_retranslated_by_the_selected_cli(tmp_cfg, monkeypatch, size, cli_fails):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.runner = 'claude'
    tmp_cfg.agent.model = 'claude-haiku-4-5'
    tmp_cfg.agent.args = ['--effort', 'high']
    tmp_cfg.raw['site'] = {'translation_batch_size': size}
    selected = copy.deepcopy(tmp_cfg.agent)
    source = '{{0}} 설명'
    original = {'strings': {'{{0}} 기존 설명': '{{0}} existing description.',
                            source: '{"text": "{{0}} description."}'}}
    calls = []

    class Agent:
        def __init__(self, cfg, dump):
            assert cfg is tmp_cfg.agent
            assert cfg == selected

        def chat(self, system, user, **kwargs):
            calls.append(user)
            assert tmp_cfg.agent == selected
            assert 'response_schema' in kwargs
            if cli_fails:
                raise RuntimeError('Selected CLI failed.')
            request = json.loads(user)
            if size == 1:
                assert request['source'] == source
                return json.dumps({'text': '{{0}} description.'})
            assert list(request['texts'].values()) == [source]
            return json.dumps({'translations': {key: '{{0}} description.' for key in request['texts']}})

    monkeypatch.setattr('sdd.translation.Agent', Agent)
    if cli_fails:
        with pytest.raises(RuntimeError, match='Selected CLI failed'):
            translate_missing(tmp_cfg, original)
        assert len(calls) == 1
        assert original['strings'][source] == '{"text": "{{0}} description."}'
        assert tmp_cfg.agent == selected
        return
    result = translate_missing(tmp_cfg, original)
    assert len(calls) == 1
    assert result['strings'][source] == '{{0}} description.'
    assert result['strings']['{{0}} 기존 설명'] == '{{0}} existing description.'
    assert original['strings'][source] == '{"text": "{{0}} description."}'
    assert tmp_cfg.agent == selected


@pytest.mark.parametrize('size', [1, 2])
def test_later_failure_keeps_catalog_even_after_a_valid_string(tmp_cfg, size):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.max_retries = 0
    tmp_cfg.raw['site'] = {'translation_batch_size': size}
    catalog = {'strings': {'첫 문장': '', '{{0}} 두 번째 문장': '', '기존': 'Existing.'}}
    original = copy.deepcopy(catalog)
    class Agent:
        def chat(self, system, user, **kwargs):
            data = json.loads(user)
            if size == 1:
                return json.dumps({'text': 'First.' if data['source'] == '첫 문장' else 'Missing placeholder.'})
            return json.dumps({'translations': {'0': 'First.', '1': 'Missing placeholder.'}})
    with pytest.raises(ValueError, match='failed validation'):
        translate_missing(tmp_cfg, catalog, Agent())
    assert catalog == original
