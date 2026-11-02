"""Controlled CLI doubles measure decisions, never new public inference success."""
import hashlib
import json
import time

import pytest

from test_generated_design import generated, cli_units
from sdd.generate import Generator


@pytest.mark.parametrize('change,expected_drafts,expected_reviews', [
    ('same', 0, 0), ('question', 1, 1), ('evidence', 1, 1), ('summary', 1, 1),
    ('ui', 0, 0), ('validation-policy', 0, 0), ('grounding-policy', 0, 2), ('style', 2, 2),
])
def test_selective_calls_and_current_revalidation_matrix(cli_units, tmp_cfg, monkeypatch, change,
                                                       expected_drafts, expected_reviews):
    section, model, save, calls, state, agent = cli_units
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='detail', question=topic['question'], sources=['stop'])]
    tmp_cfg.raw['review']['design_grounding'] = True
    state['interrupt'] = False
    # Summary and detail are intentionally different source-supported answers.
    # This remains a controlled transport double, never a stored real response.
    from sdd import cli_agent
    original_run = cli_agent.run
    def run(argv, **kwargs):
        result = original_run(argv, **kwargs)
        if 'opening summary of the topic' in kwargs['prompt'] and 'Audit factual entailment' not in kwargs['prompt']:
            envelope = json.loads(result.stdout)
            content = json.loads(envelope['result'])
            content['statements'][0]['text'] = '`stop()`은 종료 시 대기 중인 요청을 취소하는 함수를 호출합니다.'
            envelope['result'] = json.dumps(content, ensure_ascii=False)
            import subprocess
            return subprocess.CompletedProcess(argv, result.returncode, json.dumps(envelope), result.stderr)
        return result
    monkeypatch.setattr(cli_agent, 'run', run)
    save()
    Generator(tmp_cfg, model, agent()).run()
    before = list(calls)
    if change == 'question':
        topic['parts'][0]['question'] += ' 종료 조건도 확인하세요.'
    elif change == 'evidence':
        row = model.evidence['device/stop/stop']
        row['text'] += ' // changed'
        row['sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
    elif change == 'summary':
        topic['parts'].insert(0, dict(id='core', role='summary', question='종료의 핵심 결론은 무엇입니까?', sources=['stop']))
    elif change == 'ui':
        tmp_cfg.raw['site'] = dict(title='Changed shared UI title')
    elif change == 'validation-policy':
        monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'changed': 'current-checks'})
    elif change == 'grounding-policy':
        monkeypatch.setattr('sdd.grounding.policy_hash', lambda: 'new-independent-review-policy')
    elif change == 'style':
        path = tmp_cfg.style_dir/'README.md'
        path.write_text(path.read_text(encoding='utf-8')+'\n집필 규칙 추가입니다.\n', encoding='utf-8')
    save()
    started = time.perf_counter()
    Generator(tmp_cfg, model, agent()).run()
    elapsed = time.perf_counter()-started
    fresh = calls[len(before):]
    drafts = [kind for kind in fresh if kind != 'grounding']
    reviews = fresh.count('grounding')
    assert len(drafts) == expected_drafts
    assert reviews == expected_reviews
    if change in ('question', 'evidence', 'summary'):
        assert drafts == ['stop']  # zero drafting outside the changed question
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    latest = max(runs, key=lambda row: row['started_at'])
    assert latest['counts']['failed'] == 0
    report = dict(case=change, transport='controlled CLI double; no real model call',
                  new_drafts=len(drafts), new_grounding_reviews=reviews,
                  reused=latest['counts']['reused'], revalidated=latest['counts']['revalidated'],
                  failed=latest['counts']['failed'], seconds=elapsed,
                  unnecessary_outside_generation=0)
    (tmp_cfg.build_dir/f'matrix-{change}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
