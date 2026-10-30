import hashlib
import json

import pytest

from sdd.facts.model import KnowledgeModel
from sdd.translation_context import collect, unchanged_across_commits, retained_carryover


def catalog(commit, *, text='void Engine::stop() { waiting.swap(queue); }', line=10,
            actor='Engine::stop()', enclosing=False):
    record = dict(status='available', commit=commit, file='engine.cpp', line=line,
                  end_line=line, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    if enclosing:
        context = '// Scope condition\n' + text
        record['context'] = dict(line=line-1, end_line=line, text=context,
                               sha256=hashlib.sha256(context.encode()).hexdigest())
    model = KnowledgeModel(meta={'source_commit': commit}, evidence={'s/t/e': record})
    refs = json.dumps([[f'engine.cpp:{line}', 'source']])
    document = f"<p data-sdd-evidence='{refs}'><code>{actor}</code>은 대기 요청을 옮깁니다.</p>"
    contexts, sources = {}, {}
    collect(document, model, contexts, sources)
    return dict(source_commit=commit, translation_contexts=contexts, source_contexts=sources)


def test_exact_source_context_survives_a_new_commit_without_new_inference():
    old, new = catalog('a'*40), catalog('b'*40)
    key = next(iter(old['translation_contexts']))
    assert old['translation_contexts'][key] != new['translation_contexts'][key]
    assert unchanged_across_commits(old, new, key)


@pytest.mark.parametrize('change', [
    {'text': 'void Engine::stop() { cancelAll(); }'},
    {'line': 11},
    {'actor': 'Engine::flush()'},
    {'enclosing': True},
])
def test_changed_code_location_subject_or_scope_requires_translation(change):
    old, new = catalog('a'*40), catalog('b'*40, **change)
    assert not unchanged_across_commits(old, new, next(iter(old['translation_contexts'])))


def test_damaged_historical_source_is_rejected_instead_of_carried():
    old, new = catalog('a'*40), catalog('b'*40)
    next(iter(old['source_contexts'].values()))['text'] += ' altered'
    with pytest.raises(ValueError, match='context identity'):
        unchanged_across_commits(old, new, next(iter(old['translation_contexts'])))


def test_unpinned_or_same_commit_is_not_a_cross_commit_carryover():
    old = catalog('a'*40)
    key = next(iter(old['translation_contexts']))
    assert not unchanged_across_commits(old, old, key)
    assert not unchanged_across_commits(old, catalog('legacy-revision'), key)


def test_catalog_refresh_records_carryover_and_preserves_output_on_bad_history(tmp_cfg, monkeypatch):
    from sdd import export_site
    from sdd.localization_cli import prepare_catalog
    old, new = catalog('a'*40), catalog('b'*40)
    key = next(iter(old['translation_contexts']))
    old['strings'] = {key: '{{0}} moves waiting requests.'}
    record = {k: v for k, v in next(iter(new['source_contexts'].values())).items()
              if k != 'source_commit'}
    model = KnowledgeModel(meta={'source_commit': 'b'*40},
        evidence={'s/t/e': {**record, 'commit': 'b'*40, 'status': 'available'}})
    model.save(tmp_cfg.facts_path)
    refs = json.dumps([['engine.cpp:10', 'source']])
    document = f"<p data-sdd-evidence='{refs}'><code>Engine::stop()</code>은 대기 요청을 옮깁니다.</p>"
    def render(cfg, out, **kwargs):
        out.mkdir(exist_ok=True)
        (out/'page.html').write_text(document, encoding='utf-8')
        (out/'assets').mkdir()
        (out/'assets/search.json').write_text('[]', encoding='utf-8')
        return out
    monkeypatch.setattr(export_site, '_render_site', render)
    monkeypatch.setattr('sdd.translation_context.git_loader',
                        lambda *args: lambda file: '\n'*9 + record['text'])
    path = tmp_cfg.root/'english.json'
    path.write_text(json.dumps(old), encoding='utf-8')
    original = path.read_bytes()
    prepare_catalog(tmp_cfg, path)
    refreshed = json.loads(path.read_bytes())
    assert refreshed['strings'][key] == old['strings'][key]
    assert refreshed['source_commit'] == 'b'*40
    assert refreshed['review_status'] == 'human-review-pending'
    lineage = refreshed['source_carryover']
    assert lineage['from_catalog_sha256'] == hashlib.sha256(original).hexdigest()
    assert lineage['from_source_commit'] == 'a'*40
    assert lineage['source_string_sha256'] == [hashlib.sha256(key.encode()).hexdigest()]
    prepare_catalog(tmp_cfg, path)
    assert json.loads(path.read_bytes())['source_carryover'] == lineage
    assert retained_carryover(refreshed, {key: ''}) is None
    assert retained_carryover(refreshed, {key: 'A new translation.'}) is None
    next(iter(old['source_contexts'].values()))['text'] += ' modified'
    path.write_text(json.dumps(old), encoding='utf-8')
    damaged = path.read_bytes()
    with pytest.raises(ValueError, match='context identity'):
        prepare_catalog(tmp_cfg, path)
    assert path.read_bytes() == damaged
