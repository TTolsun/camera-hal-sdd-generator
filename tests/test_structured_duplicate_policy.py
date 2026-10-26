"""Structured answers keep source-aware duplication and all other prose gates."""
import copy

import pytest

from sdd.generated_design import validate_answers
from sdd.manuscript import lint
from test_duplicates import REPEATED
from test_generated_design import generated


def test_structured_validation_keeps_its_source_context(generated, monkeypatch):
    section, model, _, agent = generated
    monkeypatch.setattr('sdd.duplicates.body_findings',
                        lambda _: pytest.fail('Source-aware validation must not lose its source context'))
    validate_answers(model, section, {'stop': [agent.statement]})


def test_repetition_inside_one_structured_paragraph_is_still_rejected(generated):
    section, model, _, agent = generated
    statement = copy.deepcopy(agent.statement)
    statement['text'] += ' ' + statement['text']
    with pytest.raises(ValueError, match='중복|되풀이|반복'):
        validate_answers(model, section, {'stop': [statement]})


def test_other_prose_rules_are_still_applied_to_structured_answers(generated):
    section, model, _, agent = generated
    statement = copy.deepcopy(agent.statement)
    statement['text'] = '`stop()`은 대기 중인 요청을 취소한다.'
    with pytest.raises(ValueError, match='종결어미'):
        validate_answers(model, section, {'stop': [statement]})


def test_unstructured_prose_keeps_the_citation_duplicate_gate():
    first, second = REPEATED[0]
    findings = lint(first + ' `src/a.cpp:10`\n\n' + second + ' `src/a.cpp:10`')
    assert any(item.rule == '의미 중복 문장' for item in findings)
