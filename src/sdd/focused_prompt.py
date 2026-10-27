"""Short factual drafting, separate from page composition and validation policy."""
from __future__ import annotations

import json


OUTPUT = ('질문의 모든 조건에 답하는 한 문단. 여러 문장을 써도 됩니다.')


def system_prompt(cfg, mode=None):
    if mode is None:
        mode = cfg.review.design_prompt
    mode = cfg.review.prompt_mode(mode)
    if mode == 'standard':
        return None
    path = cfg.prompts_dir / 'focused-design-system.md'
    if not path.is_file() or not path.read_text(encoding='utf-8').strip():
        raise ValueError('focused 모드에는 비어 있지 않은 focused-design-system.md가 필요합니다.')
    return path.read_text(encoding='utf-8').strip()


def user_prompt(topic, sources, requirements=None):
    example = {'statements': [{'text': OUTPUT, 'quote_id': '직접 근거의 구절 ID',
                               'covers': topic['covers'], 'kind': 'behavior'}]}
    question = topic['question']
    if requirements:
        question += '\n함께 답할 항목:\n' + json.dumps(requirements, ensure_ascii=False)
    constraints = {key: topic[key] for key in ('_statement_kind', '_max_statements') if key in topic}
    if 'answer_contract' in topic:
        constraints['answer_contract'] = {key: value for key, value in topic['answer_contract'].items()
                                          if key in ('basis', 'required_terms')}
    return ('근거:\n' + json.dumps(sources, ensure_ascii=False)
            + '\n질문: ' + question
            + '\n작성 조건: ' + json.dumps(constraints, ensure_ascii=False)
            + '\n문장은 합니다·입니다 형태로 끝내세요. 한 문단은 600자·4문장 이내로 쓰고, '
              '필수 용어의 각 묶음에서 하나 이상을 원래 표기대로 포함하세요. '
              '질문 밖의 함수 내부나 추가 조사 과제를 덧붙이지 마세요. '
              '질문에서 요구한 사항을 확인할 수 없을 때만 확인되지 않은 대상을 짧게 밝히세요. '
              '제공된 코드·제공된 근거 같은 작성 과정 표현은 쓰지 말고, 같은 내용을 바꿔 말하지 마세요.'
            + '\n출력: '
            + json.dumps(example, ensure_ascii=False)
            + ' 형식의 JSON만 반환하세요.')


def reuse_policy(cfg, system):
    # Editorial rules still govern the assembled document. A policy edit must
    # invalidate old answers even when the model receives a shorter instruction.
    styles = {p.name: p.read_text(encoding='utf-8') for p in sorted(cfg.style_dir.glob('*.md'))}
    return json.dumps({'system': system, 'evidence_format': 'scoped-whole-source-v1', 'template': user_prompt(
        {'question': '', 'covers': []}, {}, {'id': 'question'}), 'styles': styles}, ensure_ascii=False, sort_keys=True)
