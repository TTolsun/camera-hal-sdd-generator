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
