import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from sdd import translation_context
from sdd.site_localization import DisplayText
from sdd.translation import translate_missing


def inputs():
    source = 'void Engine::stop() { waiting.swap(queue); stopDevice(); }'
    record = dict(status='available', commit='revision-a', file='engine.cpp', line=10, end_line=10,
                  text=source, sha256=hashlib.sha256(source.encode()).hexdigest())
    model = SimpleNamespace(meta={'source_commit': 'revision-a'}, evidence={'s/t/e': record})
    refs = json.dumps([['engine.cpp:10', 'source']])
    document = '<p data-sdd-evidence=\'' + refs + '\'><code>Engine::stop()</code>은 먼저 대기 요청을 옮깁니다.</p>'
    return document, model


def test_inline_context_is_read_only_and_cited_source_is_authenticated():
    document, model = inputs()
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool)
    key = next(iter(contexts))
    assert key == '{{0}}은 먼저 대기 요청을 옮깁니다.'
    context = translation_context.for_source(dict(source_commit='revision-a',
        translation_contexts=contexts, source_contexts=pool), key)[0]
    assert context['inline_tokens'] == {'{{0}}': 'Engine::stop()'}
    assert context['sources'][0]['text'] == model.evidence['s/t/e']['text']
    a, b = DisplayText(lambda value: value), DisplayText(lambda value: value, context_observer=lambda *args: None)
    a.feed(document); b.feed(document)
    assert a.output == b.output


@pytest.mark.parametrize('failure', ['hash', 'context-hash', 'context-file', 'context-commit'])
def test_corrupt_or_mixed_source_context_fails(failure):
    document, model = inputs()
    record = model.evidence['s/t/e']
    if failure == 'hash':
        record['sha256'] = '0' * 64
    else:
        record['context'] = copy.deepcopy(record)
        if failure == 'context-hash': record['context']['sha256'] = '0' * 64
        elif failure == 'context-file': record['context']['file'] = 'other.cpp'
        else: record['context']['source_commit'] = 'revision-b'
    with pytest.raises(ValueError, match='Translation source'):
        translation_context.collect(document, model, {}, {})


def test_native_translation_receives_context_but_retains_opaque_output_contract(tmp_cfg):
    document, model = inputs()
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool)
    key = next(iter(contexts))
    catalog = dict(strings={key: ''}, source_commit='revision-a',
                   translation_contexts=contexts, source_contexts=pool)
    tmp_cfg.agent.kind = 'ollama'
    class Agent:
        def chat(self, system, user, **kwargs):
            payload = json.loads(user)
            assert payload['source'] == key
            assert payload['read_only_context']['source'][0]['sources'][0]['text'] == model.evidence['s/t/e']['text']
            return json.dumps({'text': '{{0}} first moves the waiting requests.'})
    result = translate_missing(tmp_cfg, catalog, Agent())
    assert result['strings'][key].startswith('{{0}}')
    broken = copy.deepcopy(catalog)
    next(iter(broken['source_contexts'].values()))['source_commit'] = 'revision-b'
    with pytest.raises(ValueError, match='context identity or source commit'):
        translation_context.for_source(broken, key)


def test_context_counts_towards_the_unchanged_input_budget(tmp_cfg):
    document, model = inputs()
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool)
    key = next(iter(contexts))
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.agent.max_input_chars = 700
    tmp_cfg.raw['site'] = {'translation_batch_size': 2}
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            assert len(system) + len(user) <= 700
            return json.dumps({'translations': {'0': '{{0}} first moves the waiting requests.'}})
    agent = Agent()
    assert translate_missing(tmp_cfg, {'strings': {key: ''}}, agent)['strings'][key]
    agent.calls = 0
    catalog = dict(strings={key: ''}, source_commit='revision-a',
                   translation_contexts=contexts, source_contexts=pool)
    with pytest.raises(ValueError, match='input exceeds the configured budget'):
        translate_missing(tmp_cfg, catalog, agent)
    assert agent.calls == 0


def test_catalog_reuses_unchanged_context_and_invalidates_changed_binding(tmp_cfg, monkeypatch):
    from sdd import export_site
    from sdd.facts.model import KnowledgeModel
    from sdd.localization_cli import prepare_catalog
    document, fake = inputs()
    model = KnowledgeModel(meta=fake.meta, evidence=fake.evidence)
    monkeypatch.setattr(translation_context, 'git_loader', lambda *args: lambda file: '\n' * 9 + model.evidence['s/t/e']['text'])
    model.save(tmp_cfg.facts_path)
    def render(cfg, out, **kwargs):
        out.mkdir(exist_ok=True)
        (out/'page.html').write_text(document, encoding='utf-8')
        (out/'assets').mkdir()
        (out/'assets/search.json').write_text('[]', encoding='utf-8')
        return out
    monkeypatch.setattr(export_site, '_render_site', render)
    path = tmp_cfg.root/'english.json'
    prepare_catalog(tmp_cfg, path)
    catalog = json.loads(path.read_text(encoding='utf-8'))
    key = next(iter(catalog['strings']))
    catalog['strings'][key] = '{{0}} first moves the waiting requests.'
    path.write_text(json.dumps(catalog), encoding='utf-8')
    prepare_catalog(tmp_cfg, path)
    assert json.loads(path.read_text(encoding='utf-8'))['strings'][key] == catalog['strings'][key]
    document = document.replace('Engine::stop', 'Other::stop')
    record = model.evidence['s/t/e']
    record['text'] = record['text'].replace('Engine::stop', 'Other::stop')
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    model.meta['source_commit'] = 'revision-b'
    record['commit'] = 'revision-b'
    model.save(tmp_cfg.facts_path)
    prepare_catalog(tmp_cfg, path)
    assert json.loads(path.read_text(encoding='utf-8'))['strings'][key] == ''


def test_enclosing_evidence_is_inherited_without_changing_html():
    document, model = inputs()
    document = document.replace('<p ', '<section ').replace('</p>', '</p></section>').replace('><code>', '><p><code>')
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool)
    assert next(iter(contexts.values()))[0]['source_ids']


@pytest.mark.parametrize('change', ['missing-commit', 'wrong-commit', 'wrong-range', 'wrong-offset', 'unrelated-context'])
def test_declared_source_cannot_be_relabelled_or_bound_to_another_excerpt(change):
    document, model = inputs()
    record = model.evidence['s/t/e']
    if change == 'missing-commit': record.pop('commit')
    elif change == 'wrong-commit': record['commit'] = 'revision-b'
    else:
        record['context'] = copy.deepcopy(record)
        context = record['context']
        if change == 'wrong-range': context.update(line=11, end_line=11)
        elif change == 'wrong-offset':
            context.update(line=8, end_line=10, text='\n' + record['text'] + '\n')
        else: context['text'] = 'void Other::stop() {}'
        context['sha256'] = hashlib.sha256(context['text'].encode()).hexdigest()
    with pytest.raises(ValueError, match='Translation source'):
        translation_context.collect(document, model, {}, {})


@pytest.mark.parametrize('refs', [['missing.cpp:10', 'source'], ['engine.cpp:not-a-line', 'source']])
def test_declared_unresolvable_source_is_not_silently_omitted(refs):
    document, model = inputs()
    document = document.replace(json.dumps([['engine.cpp:10', 'source']]), json.dumps([refs]))
    with pytest.raises(ValueError, match='translation source|Translation source'):
        translation_context.collect(document, model, {}, {})


def test_structural_citation_uses_the_whole_pinned_file_without_truncation():
    document, model = inputs()
    text = '\n' * 9 + model.evidence['s/t/e']['text']
    model.evidence = {}
    model.citations = {'engine.cpp:10'}
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool, lambda file: text)
    assert next(iter(pool.values()))['text'] == text


def test_archive_cannot_restore_a_translation_with_a_different_context(tmp_cfg):
    document, model = inputs()
    contexts, pool = {}, {}
    translation_context.collect(document, model, contexts, pool)
    key = next(iter(contexts))
    catalog = dict(strings={key: ''}, source_commit='revision-a', translation_contexts=contexts, source_contexts=pool)
    old_context = translation_context.for_source(catalog, key)
    record = {'request': {'user': json.dumps({'texts': {'old': key}, 'read_only_context': {'old': old_context}})}}
    catalog['translation_contexts'][key][0]['resolved_source'] += ' A changed binding.'
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.raw['site'] = {'translation_batch_size': 2}
    class Agent:
        calls = 0
        reused = 0
        def translation_candidates(self, system):
            yield record, {'old': key}, {'old': '{{0}} stale translation.'}
        def record_translation_reuse(self, *args): self.reused += 1
        def chat(self, system, user, **kwargs):
            self.calls += 1
            assert 'A changed binding.' in user
            return json.dumps({'translations': {'0': '{{0}} first moves waiting requests.'}})
    agent = Agent()
    assert 'stale' not in translate_missing(tmp_cfg, catalog, agent)['strings'][key]
    assert agent.calls == 1 and agent.reused == 0
    assert translation_context.matches_archive(record, 'old', dict(catalog, translation_contexts=contexts), key) is False
