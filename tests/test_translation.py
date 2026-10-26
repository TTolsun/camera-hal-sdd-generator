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


def test_translation_retry_preserves_only_validated_checkpoint(tmp_cfg, monkeypatch):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw.setdefault('review', {})['answer_cache'] = True
    monkeypatch.setattr('sdd.answer_cache.model_digest', lambda _: 'weights-v1')
    catalog = {'strings': {'첫 문장': '', '{{0}} 두 번째 문장': ''}}
    class Agent:
        def __init__(self, fail):
            self.fail, self.calls = fail, []
        def chat(self, system, user, **kwargs):
            self.calls.append(user)
            source = json.JSONDecoder().raw_decode(user)[0]['source']
            return json.dumps({'text': 'First sentence.' if source == '첫 문장' else
                               'Missing placeholder.' if self.fail else '{{0}} second sentence.'})
    with pytest.raises(ValueError, match='failed validation'):
        translate_missing(tmp_cfg, catalog, Agent(True))
    assert len(list((tmp_cfg.build_dir/'validated-answers').glob('*.json'))) == 1
    retry = Agent(False)
    assert translate_missing(tmp_cfg, catalog, retry)['strings']['첫 문장'] == 'First sentence.'
    assert len(retry.calls) == 1
    # A source change needs a new translation, even with the same checkpoint.
    translate_missing(tmp_cfg, {'strings': {'{{0}} 수정한 문장': ''}}, retry)
    assert len(retry.calls) == 2


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


def test_bilingual_diagram_labels_are_reused_without_retranslation(tmp_path):
    from sdd.localization_cli import diagram_translations
    def write(name, translated):
        (tmp_path/name).write_text('flowchart TB\n%% sdd:translations ' + json.dumps(
            {'변경 가능, <br/>확인 의무': translated}, ensure_ascii=False) + '\n', encoding='utf-8')
    write('one.mmd', 'May have changed; <br/>must check')
    assert diagram_translations(tmp_path) == {'변경 가능, 확인 의무': 'May have changed; must check'}
    write('two.mmd', 'Now permitted')
    with pytest.raises(ValueError, match='Conflicting'):
        diagram_translations(tmp_path)


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


def test_batch_preserves_binding_obligations_like_single_translation(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 6}
    source = '호출자는 변경된 구성을 확인해야 합니다.'
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            if self.calls == 2:
                assert 'Translation ID 0' in user and 'should weakens the contract' in user
            return json.dumps({'translations': {'0': 'The caller ' +
                ('should' if self.calls == 1 else 'must') + ' check the changed configuration.'}})
    agent = Agent()
    translated = translate_missing(tmp_cfg, {'strings': {source: ''}}, agent)
    assert agent.calls == 2 and 'must' in translated['strings'][source]


def test_reported_documentation_request_is_not_a_binding_api_obligation():
    from sdd.translation import _check_obligation
    source = '{{0}} 주석은 타이밍 정보를 문서화해야 함을 요청합니다.'
    translated = 'The {{0}} comment requests that timing information be documented.'
    _check_obligation(source, translated)
    with pytest.raises(ValueError, match='binding obligation'):
        _check_obligation(source + ' 호출자는 버퍼를 유지해야 합니다.', translated)


def test_translation_http_replay_survives_batch_id_change_and_rechecks_source(tmp_cfg, monkeypatch):
    from sdd.llm import Agent
    from sdd.design_replay import Archive
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 6}
    calls = []
    def respond(self, system, user, response_schema=None):
        calls.append(user)
        texts, _ = json.JSONDecoder().raw_decode(user)
        return json.dumps({'translations': {k: '{{0}} process.' for k in texts['texts']}})
    monkeypatch.setattr(Agent, '_ollama', respond)
    dump = tmp_cfg.build_dir/'translation-prompts'
    first = translate_missing(tmp_cfg, {'strings': {'{{0}} 처리': ''}}, Agent(tmp_cfg.agent, dump))
    assert first['strings']['{{0}} 처리'] == '{{0}} process.'
    replay = Archive(dump/'calls', tmp_cfg.agent).reviewer(Agent(tmp_cfg.agent, dump))
    second = translate_missing(tmp_cfg, {'strings': {'기존': 'Existing.', '{{0}} 처리': ''}}, replay)
    assert second['strings']['{{0}} 처리'] == '{{0}} process.'
    assert len(calls) == 1 and replay.replayed_http_calls == 1
    assert replay.translation_replays[0]['source_sha256']
    translate_missing(tmp_cfg, {'strings': {'{{0}} 수정한 처리': ''}}, replay)
    assert len(calls) == 2


def test_batch_retries_only_failed_item_with_exact_missing_placeholder(tmp_cfg):
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 6}
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            texts, _ = json.JSONDecoder().raw_decode(user)
            if self.calls == 1:
                return json.dumps({'translations': {'0': 'First.', '1': '{{0}} gets a value.'}})
            assert set(texts['texts']) == {'1'}
            assert 'Translation ID 1' in user and '{{2}}' in user and 'Missing:' in user
            return json.dumps({'translations': {'1': '{{0}} gets {{2}}.'}})
    agent = Agent()
    result = translate_missing(tmp_cfg, {'strings': {'첫 문장': '', '{{0}} 에 {{2}} 대입': ''}}, agent)
    assert agent.calls == 2 and result['strings']['첫 문장'] == 'First.'


def test_translation_replay_does_not_adopt_invalid_batch_extra_fields(tmp_cfg, monkeypatch):
    from sdd.llm import Agent
    from sdd.design_replay import Archive
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 6}
    calls, invalid = [], [True]
    def respond(self, system, user, response_schema=None):
        calls.append(user)
        texts, _ = json.JSONDecoder().raw_decode(user)
        response = {'translations': {k: 'English.' for k in texts['texts']}}
        if invalid[0]: response['extra'] = 'Not permitted by the current validator'
        return json.dumps(response)
    monkeypatch.setattr(Agent, '_ollama', respond)
    dump = tmp_cfg.build_dir/'translation-prompts'
    with pytest.raises(ValueError, match='batch failed'):
        translate_missing(tmp_cfg, {'strings': {'문장': ''}}, Agent(tmp_cfg.agent, dump))
    before = len(calls)
    invalid[0] = False
    replay = Archive(dump/'calls', tmp_cfg.agent).reviewer(Agent(tmp_cfg.agent, dump))
    assert translate_missing(tmp_cfg, {'strings': {'문장': ''}}, replay)['strings']['문장'] == 'English.'
    assert len(calls) == before + 1 and replay.replayed_http_calls == 0
