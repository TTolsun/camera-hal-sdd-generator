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
            if self.calls == 2:
                assert "Missing: ['{{0}}']" in user
                assert 'unexpected or repeated: []' in user
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
    from sdd.glossary import glossary_file
    path = glossary_file(tmp_cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('terms:\n- term: 디베이어\n  definition: 색 정보를 복원합니다.\n', encoding='utf-8')
    # A UI action label is not terminology for the noun used in prose.
    catalog = {'strings': {'디베이어': 'Debayering', '구성': 'Configure', '디베이어 구성을 확인하세요.': ''}}
    class Agent:
        def chat(self, system, user, **kwargs):
            request = json.loads(user)
            assert request['known_terms'] == {'디베이어': 'Debayering'}
            return '{"text": "Check debayering."}'
    assert translate_missing(tmp_cfg, catalog, Agent())['strings']['디베이어 구성을 확인하세요.'] == 'Check debayering.'


def test_translation_retries_weakened_obligation_without_changing_source(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    source = '호출자는 변경되었을 수 있는 구성을 확인해야 합니다.'
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            if self.calls == 2:
                assert 'should weakens the contract' in user
                assert source in user
            return json.dumps({'text': 'The caller ' + ('should' if self.calls == 1 else 'must') +
                               ' check the configuration, which may have changed.'})
    agent = Agent()
    result = translate_missing(tmp_cfg, {'strings': {source: ''}}, agent)
    assert agent.calls == 2
    assert 'must' in result['strings'][source] and 'may' in result['strings'][source]
