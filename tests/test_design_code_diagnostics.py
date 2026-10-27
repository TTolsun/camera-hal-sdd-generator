"""Rejected inline-code diagnostics must not change decoding or source text."""
import copy
import hashlib
import json

import pytest

from sdd import generated_design
from sdd.facts.model import KnowledgeModel


HINT = '식별자마다 여는 백틱과 닫는 백틱을 모두 쓰고, 설명 문장은 백틱 밖에 쓰세요.'
INCOMPLETE_SPAN = ('`exportFrameBuffers 를 호출하여 얻은 `ret` 값을 반환할 때, '
                   '`if (ret < 0)` 조건문의 본문에 속하지 않으며 모든 경로를 거치는 '
                   '별도 반환 지점에서 부호를 검사 없이 무조건 `return ret;` 합니다.')


@pytest.fixture
def unit():
    code = ('// framebuffer_allocator\nint ret = exportFrameBuffers();\n'
            'if (ret < 0)\n    buffers_.erase(it);\nreturn ret;')
    source = {'id': 'return-code', 'file': 'framebuffer_allocator.cpp',
              'start': '// framebuffer_allocator', 'end': 'return ret;'}
    topic = dict(id='return', title='반환 위치', question='반환값과 조건을 설명하세요.',
                 covers=['return'], sources=[source])
    section = dict(id='allocator', title='할당 계약', design_generation='llm',
                   design_requirements=[dict(id='return', question=topic['question'])],
                   design_topics=[topic])
    model = KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence={
        'allocator/return/return-code': dict(selector=source, commit='a' * 40,
            file=source['file'], line=10, end_line=15, text=code,
            sha256=hashlib.sha256(code.encode()).hexdigest(), status='available')})
    sources = {'return-code': code}
    _, passages = generated_design.source_passages(sources, whole_source=True)
    return model, section, topic, sources, passages


def decode(unit, text, *, quote=None):
    model, section, topic, sources, passages = unit
    statement = dict(text=text, covers=['return'], kind='behavior', evidence=['return-code'])
    statement.update({'quote_id': 'return-code:0'} if quote is None else {'quote': quote})
    raw = json.dumps({'statements': [statement]}, ensure_ascii=False)
    before = copy.deepcopy((model.evidence, section, sources, passages))
    try:
        return generated_design.decode_unit(model, section, topic, raw, sources, passages)
    finally:
        assert raw == json.dumps({'statements': [statement]}, ensure_ascii=False)
        assert (model.evidence, section, sources, passages) == before


def test_real_incomplete_span_keeps_original_error_and_adds_repair_hint(unit):
    with pytest.raises(ValueError) as rejected:
        decode(unit, INCOMPLETE_SPAN)
    assert HINT in str(rejected.value)
    original = rejected.value.__cause__
    assert isinstance(original, ValueError)
    assert '코드 표기 없는 클래스 이름' in str(original)
    assert 'framebuffer_allocator' in str(original)
    assert str(rejected.value).startswith(str(original) + ' / ')


@pytest.mark.parametrize('text', [
    '`ret` 값을 반환합니다.',
    '``ret`` 값을 반환합니다.',
    '``ret`literal`` 값을 반환합니다.',
    r'기호 \` 하나와 `ret` 값을 설명합니다.',
    r'기호 \`와 \`를 설명합니다.',
])
def test_balanced_or_escaped_code_keeps_existing_validation_error(unit, text):
    with pytest.raises(ValueError) as rejected:
        decode(unit, text, quote='An unrelated source passage not present in the input.')
    assert str(rejected.value).startswith('quote가 연결된 소스 발췌의 실제 원문과 일치하지 않습니다:')
    assert HINT not in str(rejected.value)
    assert rejected.value.__cause__ is None


@pytest.mark.parametrize('text', [
    '`ret` 값을 반환합니다.',
    '``ret`` 값을 반환합니다.',
    '``ret`literal`` 값을 반환합니다.',
    r'기호 \` 하나와 `ret` 값을 설명합니다.',
    r'기호 \`와 \`를 설명합니다.',
    'ret 값을 반환합니다.',
])
def test_code_literals_keep_existing_validation_and_normalization(unit, text):
    model, section, topic, sources, _ = unit
    expected = [dict(text=text, covers=['return'], kind='behavior', evidence=['return-code'],
                     quote=sources['return-code'])]
    generated_design.normalize_answer(model, expected, [*sources.values(), topic['question']])
    try:
        generated_design.validate_answers(model, section, {topic['id']: expected})
    except ValueError as original:
        with pytest.raises(ValueError) as rejected:
            decode(unit, text)
        assert str(rejected.value) == str(original)
        assert HINT not in str(rejected.value)
    else:
        assert decode(unit, text) == expected


def test_an_accepted_literal_is_not_rejected_by_the_diagnostic(unit):
    model, _, topic, _, _ = unit
    topic['sources'][0]['file'] = 'allocator.cpp'
    model.evidence['allocator/return/return-code']['file'] = 'allocator.cpp'
    text = '특수 문자 ` 하나를 표시합니다.'
    assert decode(unit, text)[0]['text'] == text


def test_even_backslashes_do_not_escape_an_unmatched_delimiter(unit):
    with pytest.raises(ValueError) as rejected:
        decode(unit, r'기호 \\`ret 값을 반환합니다.', quote='An unrelated source passage not present in the input.')
    assert HINT in str(rejected.value)
    assert 'quote가 연결된 소스 발췌' in str(rejected.value)
