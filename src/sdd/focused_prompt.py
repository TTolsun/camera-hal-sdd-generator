"""Short factual drafting, separate from page composition and validation policy."""
from __future__ import annotations

import json


OUTPUT = ('질문의 모든 조건에 답하는 한 문단. 여러 문장을 써도 됩니다.')


def system_prompt(cfg):
    mode = (cfg.raw.get('review') or {}).get('design_prompt', 'standard')
    if mode not in ('standard', 'focused'):
        raise ValueError('review.design_prompt는 standard 또는 focused여야 합니다.')
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
    return ('근거:\n' + json.dumps(sources, ensure_ascii=False)
            + '\n질문: ' + question + '\n출력: '
            + json.dumps(example, ensure_ascii=False)
            + ' 형식의 JSON만 반환하세요.')


def reuse_policy(cfg, system):
    # Editorial rules still govern the assembled document. A policy edit must
    # invalidate old answers even when the model receives a shorter instruction.
    styles = {p.name: p.read_text(encoding='utf-8') for p in sorted(cfg.style_dir.glob('*.md'))}
    return json.dumps({'system': system, 'evidence_format': 'scoped-whole-source-v1', 'template': user_prompt(
        {'question': '', 'covers': []}, {}, {'id': 'question'}), 'styles': styles}, ensure_ascii=False, sort_keys=True)
