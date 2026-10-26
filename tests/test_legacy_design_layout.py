"""Legacy paragraph compatibility preserves exact text and all validation gates."""
import copy
import hashlib

import pytest
import yaml

from sdd.evidence import contract_text, fingerprint
from sdd.facts.model import KnowledgeModel
from sdd.generated_design import digest, validate_answers, verify


@pytest.fixture
def design():
    section = dict(id='device', title='장치 계약', design_generation='llm',
                   design_requirements=[], design_topics=[])
    model = KnowledgeModel(meta={'source_commit': 'a' * 40})
    answers = {}
    for index, (tid, title, functions) in enumerate([
        ('begin', '시작 책임', [('begin', 1), ('prepare', 2), ('stage', 3)]),
        ('finish', '종료 책임', [('finish', 4), ('reset', 5)]),
    ]):
        source = dict(id='api', file=f'{tid}.cpp', start=f'int {functions[0][0]}()',
                      end=f'int {functions[-1][0]}() {{ return {functions[-1][1]}; }}')
        text = '\n'.join(f'int {name}() {{ return {value}; }}' for name, value in functions)
        section['design_requirements'].append(dict(id=tid, question=f'{title}의 반환값은 무엇입니까?'))
        section['design_topics'].append(dict(id=tid, title=title, question=f'{title}을 설명하세요.',
                                             covers=[tid], sources=[source]))
        model.evidence[f'device/{tid}/api'] = dict(
            selector=source, commit='a' * 40, file=source['file'], line=10 + index * 20,
            end_line=10 + index * 20 + len(functions) - 1, text=text,
            sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), status='available')
        answers[tid] = [dict(text=f'`{name}()` 함수는 해당 작업을 처리한 뒤 숫자 {value}을 반환합니다.',
                             quote=f'int {name}() {{ return {value}; }}',
                             evidence=['api'], covers=[tid], kind='behavior')
                        for name, value in functions]
    pinned, resolved, _ = validate_answers(model, section, answers)
    return model, section, answers, pinned, resolved


def body_for(design, grouped):
    _, section, _, pinned, resolved = design
    parts = ['# 장치 계약']
    for topic in resolved['design_topics']:
        selected = grouped[topic['id']] if isinstance(grouped, dict) else grouped
        text, gaps = contract_text(pinned, section['id'], topic, grouped=selected)
        assert not gaps
        parts.append(f"## {topic['title']}\n\n{text}")
    return '\n\n'.join(parts) + '\n'


def manuscript_for(design, body, **updates):
    model, section, answers, _, _ = design
    artifact = dict(schema=1, input_fingerprint=fingerprint(model, section),
                    answers=copy.deepcopy(answers), body_sha256=digest(body.strip()),
                    grounding_review='not-run')
    artifact.update(updates)
    metadata = yaml.safe_dump({'generated_design': artifact}, allow_unicode=True, sort_keys=False)
    return '---\n' + metadata + '---\n' + body


@pytest.mark.parametrize('grouped', [False, True, {'begin': False, 'finish': True},
                                    {'begin': True, 'finish': False}])
def test_each_topic_accepts_exact_legacy_or_grouped_layout(design, grouped):
    model, section, _, _, _ = design
    body = body_for(design, grouped)
    report = verify(model, section, manuscript_for(design, body))
    assert report['status'] == 'documented' and report['human_review'] == 'pending'


@pytest.mark.parametrize('damage', ['missing', 'changed', 'paraphrased', 'reordered', 'citation', 'mixed'])
def test_body_rehash_cannot_hide_missing_changed_or_mixed_topic_text(design, damage):
    model, section, _, pinned, resolved = design
    body = body_for(design, False)
    topic = resolved['design_topics'][0]
    legacy, _ = contract_text(pinned, section['id'], topic, grouped=False)
    paragraphs = legacy.split('\n\n')
    if damage == 'missing':
        changed = '\n\n'.join(paragraphs[:-1])
    elif damage == 'changed':
        changed = legacy.replace('숫자 1', '숫자 999')
    elif damage == 'paraphrased':
        changed = legacy.replace('처리한 뒤', '마친 후')
    elif damage == 'reordered':
        changed = '\n\n'.join(reversed(paragraphs))
    elif damage == 'citation':
        changed = legacy.replace('begin.cpp:10', 'begin.cpp:99')
    else:
        # Neither all-legacy nor the renderer's complete grouped topic.
        citation = '`begin.cpp:10`'
        changed = (' '.join(st['text'] for st in topic['statements'][:2]) + ' ' + citation
                   + '\n\n' + paragraphs[2])
    modified = body.replace(legacy, changed)
    with pytest.raises(ValueError, match='원고에 없습니다'):
        verify(model, section, manuscript_for(design, modified))


def test_legacy_compatibility_keeps_original_body_hash_check(design):
    model, section, _, _, _ = design
    original = body_for(design, False)
    manuscript = manuscript_for(design, original).replace(original, original.replace('숫자 1', '숫자 999', 1))
    with pytest.raises(ValueError, match='본문'):
        verify(model, section, manuscript)


def test_legacy_compatibility_keeps_input_fingerprint_check(design):
    model, section, _, _, _ = design
    manuscript = manuscript_for(design, body_for(design, False))
    changed = copy.deepcopy(section)
    changed['design_topics'][0]['question'] += ' 다른 질문입니다.'
    with pytest.raises(ValueError, match='입력 근거·질문'):
        verify(model, changed, manuscript)


def test_legacy_compatibility_keeps_source_commit_check(design):
    model, section, _, _, _ = design
    manuscript = manuscript_for(design, body_for(design, False))
    changed = copy.deepcopy(model)
    changed.evidence['device/begin/api']['commit'] = 'b' * 40
    with pytest.raises(ValueError):
        verify(changed, section, manuscript)


def test_legacy_compatibility_keeps_quote_validation_even_with_new_input_hash(design):
    model, section, _, _, _ = design
    body = body_for(design, False)
    changed = copy.deepcopy(model)
    record = changed.evidence['device/begin/api']
    record['text'] = record['text'].replace('return 1', 'return 999')
    record['sha256'] = hashlib.sha256(record['text'].encode('utf-8')).hexdigest()
    manuscript = manuscript_for(design, body, input_fingerprint=fingerprint(changed, section))
    with pytest.raises(ValueError, match='quote'):
        verify(changed, section, manuscript)


def test_legacy_compatibility_keeps_statement_contract_checks(design):
    model, section, answers, _, _ = design
    changed = copy.deepcopy(answers)
    changed['begin'][0]['evidence'] = ['not-a-source']
    with pytest.raises(ValueError):
        verify(model, section, manuscript_for(design, body_for(design, False), answers=changed))


@pytest.mark.parametrize('valid', [False, True])
def test_legacy_compatibility_keeps_grounding_policy_check(design, valid):
    from sdd.grounding import policy_hash

    model, section, _, _, _ = design
    manuscript = manuscript_for(design, body_for(design, False), grounding_review='passed',
                                grounding_policy=policy_hash() if valid else 'obsolete')
    if valid:
        assert verify(model, section, manuscript)['human_review'] == 'pending'
    else:
        with pytest.raises(ValueError, match='근거 대조 정책'):
            verify(model, section, manuscript)


def test_default_grouped_rendering_and_legacy_prefix_citation_order(design):
    _, section, _, pinned, resolved = design
    topic = copy.deepcopy(resolved['design_topics'][0])
    default, _ = contract_text(pinned, section['id'], topic)
    assert default == contract_text(pinned, section['id'], topic, grouped=True)[0]
    assert default.count('`begin.cpp:10`') == 1
    legacy, _ = contract_text(pinned, section['id'], topic, grouped=False)
    assert legacy.count('`begin.cpp:10`') == len(topic['statements'])
    topic['statements'][1]['kind'] = 'limitation'
    rendered, _ = contract_text(pinned, section['id'], topic, grouped=False)
    assert rendered.split('\n\n')[1].startswith('실행 확인 항목: ')


def test_legacy_rendering_preserves_duplicate_citations_within_one_statement(design):
    _, section, _, original, resolved = design
    pinned = copy.deepcopy(original)
    topic = copy.deepcopy(resolved['design_topics'][0])
    alias = {**topic['sources'][0], 'id': 'same-line'}
    topic['sources'].append(alias)
    topic['statements'][0]['evidence'].append('same-line')
    pinned.evidence['device/begin/same-line'] = {**pinned.evidence['device/begin/api'], 'selector': alias}
    legacy, gaps = contract_text(pinned, section['id'], topic, grouped=False)
    assert not gaps
    assert legacy.split('\n\n')[0].endswith('`begin.cpp:10`, `begin.cpp:10`')
    modern, gaps = contract_text(pinned, section['id'], topic)
    assert not gaps and modern.count('`begin.cpp:10`') == 1


@pytest.mark.parametrize('value', ['false', 0, None])
def test_layout_option_accepts_only_explicit_booleans(design, value):
    _, section, _, pinned, resolved = design
    with pytest.raises(ValueError, match='boolean'):
        contract_text(pinned, section['id'], resolved['design_topics'][0], grouped=value)
