import json

import pytest

from sdd.translation import translate_missing


def test_translation_keeps_existing_text_and_retries_placeholders(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    catalog = {'strings': {'기존 문장': 'Existing text.', '{{0}} 함수는 실패하면 반환합니다.': ''}}
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            return json.dumps({'text': 'Returns on failure.' if self.calls == 1 else '{{0}} returns on failure.'})
    agent = Agent()
    output = translate_missing(tmp_cfg, catalog, agent)
    assert agent.calls == 2
    assert output['strings']['기존 문장'] == 'Existing text.'
    assert output['strings']['{{0}} 함수는 실패하면 반환합니다.'] == '{{0}} returns on failure.'
    assert output['review_status'] == 'human-review-pending'
    assert catalog['strings']['{{0}} 함수는 실패하면 반환합니다.'] == ''


def test_invalid_translation_does_not_replace_catalog(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    catalog = {'strings': {'설명': ''}}
    class Agent:
        def chat(self, *args, **kwargs):
            return '{"text": "여전히 한국어"}'
    with pytest.raises(ValueError, match='failed validation'):
        translate_missing(tmp_cfg, catalog, Agent())
    assert catalog['strings']['설명'] == ''


def test_translation_receives_existing_terminology(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    catalog = {'strings': {'디베이어': 'Debayering', '디베이어를 확인하세요.': ''}}
    class Agent:
        def chat(self, system, user, **kwargs):
            request = json.loads(user)
            assert request['known_terms'] == {'디베이어': 'Debayering'}
            return '{"text": "Check debayering."}'
    assert translate_missing(tmp_cfg, catalog, Agent())['strings']['디베이어를 확인하세요.'] == 'Check debayering.'


def test_batch_preserves_placeholders_per_string_and_retries(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 3}
    catalog = {'strings': {'기존': 'Existing.', '{{0}} 처리': '', '{{1}} 반환': ''}}
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            data, _ = json.JSONDecoder().raw_decode(user)
            assert set(data['texts']) == {'1', '2'}
            return json.dumps({'translations': {
                '1': '{{1}} process' if self.calls == 1 else '{{0}} process',
                '2': '{{0}} return' if self.calls == 1 else '{{1}} return'}})
    agent = Agent()
    result = translate_missing(tmp_cfg, catalog, agent)
    assert agent.calls == 2 and result['strings']['기존'] == 'Existing.'
    assert result['strings']['{{0}} 처리'] == '{{0}} process'
    assert catalog['strings']['{{0}} 처리'] == ''


@pytest.mark.parametrize('bad', [{'translations': {'wrong': 'Text'}}, {'translations': {'0': '한국어'}}])
def test_bad_batch_preserves_original_catalog(tmp_cfg, bad):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 4}
    catalog = {'strings': {'설명': ''}}
    class Agent:
        def chat(self, *args, **kwargs):
            return json.dumps(bad)
    with pytest.raises(ValueError, match='batch failed'):
        translate_missing(tmp_cfg, catalog, Agent())
    assert catalog['strings'] == {'설명': ''}


def test_batch_splits_on_budget_without_truncation(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 4}
    tmp_cfg.agent.max_input_chars = 700
    catalog = {'strings': {('설명' * 80) + str(i): '' for i in range(4)}}
    class Agent:
        sizes = []
        def chat(self, system, user, **kwargs):
            assert len(system) + len(user) <= 700
            texts = json.loads(user)['texts']
            self.sizes.append(len(texts))
            return json.dumps({'translations': {key: 'English ' + key for key in texts}})
    agent = Agent()
    result = translate_missing(tmp_cfg, catalog, agent)
    assert len(agent.sizes) > 1 and sum(agent.sizes) == 4
    assert all(result['strings'].values())
