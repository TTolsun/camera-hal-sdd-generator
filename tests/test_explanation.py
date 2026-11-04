import copy

import pytest

from sdd.explanation import STAGES, configuration_errors, context, render, validate
from test_generated_design import generated


def plan():
    return dict(id='lifetime', question='When can the resource be reused?',
                sources=[dict(id='source', file='hal.cpp', start='start', end='end')],
                parts=[dict(id=s, question=s, sources=['source']) for s in STAGES],
                explanation=[dict(id=s, title=s.title(), parts=[s]) for s in STAGES])


@pytest.mark.parametrize('edit', ['missing', 'duplicate', 'reordered', 'empty-title', 'wrong-stage'])
def test_invalid_explanation_cannot_drop_or_reorder_required_questions(edit):
    topic = plan()
    if edit == 'missing':
        topic['explanation'].pop()
    elif edit == 'duplicate':
        topic['explanation'][-1]['parts'] = ['problem']
    elif edit == 'reordered':
        topic['explanation'][0]['parts'], topic['explanation'][1]['parts'] = ['principle'], ['problem']
    elif edit == 'empty-title':
        topic['explanation'][0]['title'] = ''
    else:
        topic['explanation'][0]['id'] = 'marketing'
    assert configuration_errors(topic)


@pytest.mark.parametrize('parts', [None, {}, [], ['invalid'], [dict(id=7)], [dict(id='')],
                                 [dict(id='same'),dict(id='same')]])
def test_invalid_parts_fail_configuration_before_rendering(parts):
    topic = plan()
    topic['parts'] = parts
    assert configuration_errors(topic)


@pytest.mark.parametrize('missing', ['question', 'sources'])
def test_public_generation_rejects_invalid_explanation_before_unit_construction(generated, tmp_cfg, missing):
    from sdd.generated_design import generate
    section, model, _, agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id=s, question=s, sources=['stop']) for s in STAGES]
    topic['explanation'] = [dict(id=s, title=s.title(), parts=[s]) for s in STAGES]
    topic['parts'][2].pop(missing)
    with pytest.raises(ValueError, match='explanation'):
        generate(tmp_cfg, model, agent, section)
    assert agent.calls == []


@pytest.mark.parametrize('sources', [None, {}, [None], [dict(id=[])], [dict(id='')]])
def test_malformed_source_bindings_rejected_by_public_preflight(generated, tmp_cfg, sources):
    from sdd.generated_design import generate
    section, model, _, agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id=s, question=s, sources=['stop']) for s in STAGES]
    topic['explanation'] = [dict(id=s, title=s.title(), parts=[s]) for s in STAGES]
    topic['sources'] = sources
    with pytest.raises(ValueError):
        generate(tmp_cfg, model, agent, section)
    assert agent.calls == []


def test_assembled_answers_keep_stage_boundaries_and_every_source_binding():
    topic = plan()
    answers = [dict(part_id=s, text=s, evidence=[s+'-source']) for s in STAGES]
    render_part = lambda selected: '|'.join(s['text']+':'+s['evidence'][0] for s in selected)
    first = render(topic, answers, render_part)
    assert first == render(topic, copy.deepcopy(answers), render_part)
    assert [first.index('### '+s.title()) for s in STAGES] == sorted(first.index('### '+s.title()) for s in STAGES)
    for answer in answers:
        assert answer['evidence'][0] in first
    for broken in (answers[:-1], answers[::-1], answers+[answers[0]]):
        with pytest.raises(ValueError, match='stage order'):
            validate(topic, broken)


def test_writer_sees_complete_question_ownership_but_only_selected_sources():
    from sdd.design_request import _design_units
    topic = plan()
    topic.update(covers=['lifetime'], sources=[dict(id='source', file='hal.cpp', start='start', end='end')])
    units = _design_units(dict(design_topics=[topic]), {})
    assert len(units) == len(STAGES)
    for stage, unit in zip(STAGES, units):
        assert unit['question'] == stage
        assert unit['sources'] == topic['sources']
        assert 'explanation' not in unit
        assert unit['_explanation_context'] == context(topic, stage)
        assert all(p['question'] in unit['_explanation_context'] for p in topic['parts'])


def test_question_source_or_stage_change_invalidates_only_affected_topic_inputs():
    from sdd.design_reuse import topic_inputs
    from sdd.facts.model import KnowledgeModel
    topic = plan()
    topic.update(covers=['lifetime'], sources=[dict(id='source', file='hal.cpp', start='start', end='end')])
    other = dict(id='unrelated', title='unrelated', question='Other?', sources=[], covers=['other'])
    section = dict(id='hal', design_topics=[topic, other],
                   design_requirements=[dict(id='lifetime', question='Lifetime?'), dict(id='other', question='Other?')])
    model = KnowledgeModel(evidence={'hal/lifetime/source': dict(text='original', sha256='old')})
    baseline = topic_inputs(model, section, 'policy')
    for kind in ('question', 'source', 'stage'):
        changed, changed_model = copy.deepcopy(section), copy.deepcopy(model)
        if kind == 'question':
            changed['design_topics'][0]['parts'][0]['question'] += ' changed'
        elif kind == 'source':
            changed_model.evidence['hal/lifetime/source'].update(text='changed', sha256='new')
        else:
            changed['design_topics'][0]['explanation'][0]['title'] += ' changed'
        after = topic_inputs(changed_model, changed, 'policy')
        assert after['lifetime'] != baseline['lifetime']
        assert after['unrelated'] == baseline['unrelated']


def test_generated_stage_labels_are_not_uncited_prose_but_answers_still_require_citations(generated, tmp_cfg):
    import hashlib
    import json
    from sdd.generate import Generator
    from sdd.generated_design import verify
    section, model, save, _ = generated
    topic = plan()
    topic.update(covers=['shutdown'], title='수명 변경 확인', sources=[])
    model.evidence = {}
    for index, stage in enumerate(STAGES):
        source = dict(id=stage, file='device.cpp', start='void '+stage+'()', end='}')
        topic['sources'].append(source)
        topic['parts'][index].update(sources=[stage], max_statements=1)
        text = 'void '+stage+'() { step'+str(index)+'(); }'
        model.evidence['device/lifetime/'+stage] = dict(selector=source, commit='a'*40,
            file='device.cpp', line=10+index, end_line=10+index, text=text,
            sha256=hashlib.sha256(text.encode()).hexdigest(), status='available')
    section['design_topics'] = [topic]
    save()
    class Writer:
        def __init__(self): self.calls = []
        def chat(self, system, user, **kwargs):
            index = len(self.calls)
            self.calls.append(user)
            stage = STAGES[index]
            return json.dumps(dict(statements=[dict(text=f'`{stage}()`은 `step{index}()`을 호출합니다.',
                quote=model.evidence['device/lifetime/'+stage]['text'], evidence=[stage], covers=['shutdown'], kind='behavior')]))
    writer = Writer()
    path = Generator(tmp_cfg, model, writer).run()[0]
    first = path.read_text(encoding='utf-8')
    assert len(writer.calls) == 5
    assert verify(model, section, first, cfg=tmp_cfg)['human_review'] == 'pending'
    from sdd.impact import ImpactReport
    Generator(tmp_cfg, model, writer).run(impact=ImpactReport('a'*40, 'a'*40, sections={'device': []}))
    assert len(writer.calls) == 5  # unchanged inputs reuse validated answers
    second = path.read_text(encoding='utf-8')
    from sdd.document_metadata import split_frontmatter
    assert split_frontmatter(first)[1] == split_frontmatter(second)[1]
    topic['explanation'][0]['title'] += ' 변경'
    save()
    with pytest.raises(ValueError, match='재생성'):
        verify(model, section, first, cfg=tmp_cfg)


def test_generated_heading_cannot_hide_an_unsupported_statement(generated):
    from sdd.design_response import materialize
    section, model, _, agent = generated
    statement = copy.deepcopy(agent.statement)
    statement['text'] = '### Problem'
    with pytest.raises(ValueError, match='구조·링크·HTML'):
        materialize(model, section, {'stop': [statement]})


@pytest.mark.parametrize('title', ['<!--', '<script>bad</script>', '[hidden](https://example.test)',
                                  '`code`', '*hidden*', 'Title {#other}', 'Title\x00hidden'])
def test_markup_stage_title_fails_generation_before_any_model_call(generated, tmp_cfg, title):
    from sdd.generate import Generator
    section, model, save, agent = generated
    topic = plan()
    topic.update(covers=['shutdown'], sources=section['design_topics'][0]['sources'])
    source = topic['sources'][0]['id']
    for part in topic['parts']:
        part['sources'] = [source]
    topic['explanation'][0]['title'] = title
    section['design_topics'] = [topic]
    save()
    with pytest.raises(ValueError, match='plain text titles'):
        Generator(tmp_cfg, model, agent).run()
    assert agent.calls == []
    assert not list(tmp_cfg.sdd_dir.glob('*.md'))


def test_markup_stage_title_cannot_pass_publishing_materialization(generated):
    from sdd.evidence import contract_text
    section, model, _, _ = generated
    topic = plan()
    topic.update(covers=['shutdown'], sources=section['design_topics'][0]['sources'])
    topic['explanation'][0]['title'] = '<!--'
    section['design_topics'] = [topic]
    for part in topic['parts']:
        part['sources'] = [topic['sources'][0]['id']]
    with pytest.raises(ValueError, match='plain text titles'):
        contract_text(model, section['id'], {**topic, 'statements': []})
