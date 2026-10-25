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
