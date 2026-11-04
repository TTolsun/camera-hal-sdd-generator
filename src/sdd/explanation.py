"""Optional explanation stages over existing source-bound parts.

This checks assembly and review scope, never causal truth or human approval.
"""
from __future__ import annotations

import json

STAGES = ('problem', 'principle', 'normal', 'conditions', 'change')


def configuration_errors(topic):
    if 'explanation' not in topic:
        return []
    stages = topic['explanation']
    parts = topic.get('parts', [])
    if (not isinstance(parts, list) or not parts
            or any(not isinstance(p, dict) or not isinstance(p.get('id'), str) for p in parts)):
        return ['explanation requires nonempty source-bound parts with string IDs.']
    if (not isinstance(stages, list) or len(stages) != len(STAGES)
            or any(not isinstance(s, dict) or set(s) != {'id', 'title', 'parts'} for s in stages)):
        return ['explanation requires five ordered stages with id, title and parts.']
    if [s['id'] for s in stages] != list(STAGES):
        return ['explanation stages must be problem, principle, normal, conditions, change.']
    if any(not isinstance(s['title'], str) or not s['title'].strip()
           or '\n' in s['title'] or '\r' in s['title']
           or not isinstance(s['parts'], list) or not s['parts']
           or any(not isinstance(p, str) for p in s['parts']) for s in stages):
        return ['explanation requires nonempty single-line titles and part ID lists.']
    if len({s['title'] for s in stages}) != len(stages):
        return ['explanation stage titles must be unique.']
    if [p for s in stages for p in s['parts']] != [p.get('id') for p in parts]:
        return ['explanation must own every part exactly once in manuscript order.']
    return []


def context(topic, part_id):
    if 'explanation' not in topic:
        return ''
    return ('\nExplanation plan (editorial scope, not source evidence):\n'
            + json.dumps({'question': topic['question'], 'stages': topic['explanation'],
                          'parts': [{'id': p['id'], 'question': p['question']} for p in topic['parts']],
                          'current_part': part_id}, ensure_ascii=False)
            + '\nAnswer only the current part using its supplied sources. Connect its condition, result '
              'and next check where requested. Other parts own their details; do not repeat their '
              'premises or fill their answers. Do not infer historical rationale or alternatives from code.')


def validate(topic, statements):
    if 'explanation' not in topic:
        return
    if errors := configuration_errors(topic):
        raise ValueError(' / '.join(errors))
    order = [p['id'] for p in topic['parts']]
    actual = [s.get('part_id') for s in statements]
    if (any(p not in order for p in actual)
            or list(dict.fromkeys(actual)) != order
            or actual != sorted(actual, key=order.index)):
        raise ValueError('explanation answers must retain every part in stage order.')


def render(topic, statements, render_part):
    validate(topic, statements)
    return '\n\n'.join('### ' + stage['title'] + '\n\n' + render_part(
        [s for s in statements if s['part_id'] in stage['parts']])
        for stage in topic['explanation'])
