import pytest

from sdd.evidence import select_span
from sdd.contract_schema import configuration_errors


TEXT = 'first {\ncontext: worker\nreturns zero\n}\nsecond {\ncontext: caller\nreturns error\n}'


def test_scope_disambiguates_identical_labels_without_including_other_contracts():
    source = dict(start='context:', end='returns error', scope=dict(start='second {', end='}'))
    begin, end = select_span(TEXT, source)
    assert TEXT[begin:end] == 'context: caller\nreturns error'
    assert TEXT[:begin].count('\n') + 1 == 6
    with pytest.raises(ValueError, match='유일'):
        select_span(TEXT, dict(start='context:', end='returns error'))


def test_scope_never_searches_past_boundary_or_chooses_ambiguous_scope():
    with pytest.raises(ValueError, match='선택 범위'):
        select_span(TEXT, dict(start='context:', end='returns error', scope=dict(start='first {', end='}')))
    for scope in [dict(start='{', end='}'), dict(start='missing', end='}')]:
        with pytest.raises(ValueError, match='유일'):
            select_span(TEXT, dict(start='context:', end='returns zero', scope=scope))


@pytest.mark.parametrize('scope', [None, {}, {'start': 'first'}, {'start': '', 'end': '}'},
                                  {'start': 'first', 'end': 2}, {'start': 'first', 'end': '}', 'scope': {}}])
def test_invalid_scope_fails_configuration(scope):
    section = {'design_topics': [{'id': 't', 'sources': [dict(id='s', file='source.cpp',
                    start='context:', end='returns zero', scope=scope)]}]}
    assert any('scope' in error for error in configuration_errors(section))


def test_collect_pins_full_scope_and_invalidates_when_only_context_changes(tmp_cfg, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    import yaml
    from sdd.evidence import collect, fingerprint
    from sdd.facts.model import KnowledgeModel
    source = dict(id='s', file='source.cpp', start='context:', end='returns error',
                  scope=dict(start='second {', end='}'))
    section = {'id': 'device', 'design_topics': [{'id': 't', 'sources': [source]}]}
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}), encoding='utf-8')
    contents = [TEXT]
    monkeypatch.setattr('sdd.evidence.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=contents[0]))
    model = KnowledgeModel(meta={'source_commit': 'a' * 40})
    collect(tmp_cfg, model)
    record = model.evidence['device/t/s']
    assert record['text'] == 'context: caller\nreturns error'
    context = record['context']
    assert context['text'] == 'second {\ncontext: caller\nreturns error\n}'
    assert context['sha256'] == hashlib.sha256(context['text'].encode()).hexdigest()
    before = fingerprint(model, section)
    selected_hash = record['sha256']
    contents[0] = TEXT.replace('second {', 'second { // changed guard')
    collect(tmp_cfg, model)
    assert model.evidence['device/t/s']['sha256'] == selected_hash
    assert fingerprint(model, section) != before
