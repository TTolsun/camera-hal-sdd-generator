import json

import pytest

from sdd import focused_prompt


def enable(cfg):
    cfg.raw['review'] = {'design_prompt': 'focused'}
    path = cfg.prompts_dir / 'focused-design-system.md'
    path.write_text('제공된 근거로 각 조건에 답하세요.', encoding='utf-8')
    return path


def test_explicit_mode_and_project_prompt(tmp_cfg):
    assert focused_prompt.system_prompt(tmp_cfg) is None
    path = enable(tmp_cfg)
    assert focused_prompt.system_prompt(tmp_cfg) == path.read_text(encoding='utf-8')
    path.unlink()
    with pytest.raises(ValueError, match='focused-design-system'):
        focused_prompt.system_prompt(tmp_cfg)
    tmp_cfg.raw['review']['design_prompt'] = 'focusd'
    with pytest.raises(ValueError, match='design_prompt'):
        focused_prompt.system_prompt(tmp_cfg)


def test_scope_excludes_editorial_and_validator_instructions():
    topic = {'question': '요청을 언제 반환합니까?', 'covers': ['completion'],
             'answer_contract': {'reject_patterns': [{'pattern': 'forbidden-regex'}]},
             'title': '다른 페이지 편집 지침', 'reader': '전체 제품 홍보'}
    sources = {'stop': [{'text': 'shall cancel', 'quote_id': 'stop:0'}]}
    prompt = focused_prompt.user_prompt(topic, sources)
    assert topic['question'] in prompt and json.dumps(sources, ensure_ascii=False) in prompt
    assert prompt.index('shall cancel') < prompt.index(topic['question']) < prompt.index('출력:')
    assert 'completion' in prompt
    assert 'forbidden-regex' not in prompt and topic['title'] not in prompt
    assert '실패 반환은 무엇입니까?' in focused_prompt.user_prompt(
        topic, sources, {'failure': '실패 반환은 무엇입니까?'})


def test_style_and_project_prompt_changes_invalidate_reuse(tmp_cfg):
    path = enable(tmp_cfg)
    def policy():
        return focused_prompt.reuse_policy(tmp_cfg, focused_prompt.system_prompt(tmp_cfg))
    old = policy()
    # Even an unnumbered editorial note must invalidate reused focused answers.
    (tmp_cfg.style_dir / 'README.md').write_text('정책이 바뀌었습니다.', encoding='utf-8')
    assert policy() != old
    old = policy()
    path.write_text('새 작성 지침입니다.', encoding='utf-8')
    assert policy() != old


def test_whole_source_keeps_guard_and_final_check_in_one_citable_passage():
    from sdd.generated_design import source_passages, resolve_passages
    code = 'void stop() {\n  if (!ready) return;\n\n  cancel();\n\n  ASSERT(empty());\n}'
    annotated, passages = source_passages({'stop': code}, whole_source=True)
    assert annotated == {'stop': [{'text': code, 'quote_id': 'stop:0'}]}
    answers = resolve_passages([dict(text='조건과 최종 검사를 설명합니다.', quote_id='stop:0',
                                    covers=['stop'], kind='behavior')], passages)
    assert answers[0]['quote'] == code
    assert len(source_passages({'stop': code})[1]) > 1
    scope = {'start': 'void stop()', 'end': '}'}
    annotated, scoped = source_passages({'stop': code}, whole_source=True, scopes={'stop': scope})
    assert annotated['stop'][0]['scope'] == scope
    assert scoped == passages  # Context never rewrites the quoted source.
    # Standard prompts also keep a scoped contract/control flow together.
    standard, standard_passages = source_passages({'stop': code}, scopes={'stop': scope})
    assert standard == annotated and standard_passages == passages


def test_section_override_preserves_project_default(tmp_cfg):
    enable(tmp_cfg)
    assert focused_prompt.system_prompt(tmp_cfg, 'standard') is None
    assert focused_prompt.system_prompt(tmp_cfg) is not None
    tmp_cfg.raw['review']['design_prompt'] = 'standard'
    assert focused_prompt.system_prompt(tmp_cfg, 'focused') is not None
    assert focused_prompt.system_prompt(tmp_cfg) is None
