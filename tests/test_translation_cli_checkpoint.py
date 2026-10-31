"""Controlled CLI archives prove resume without redoing completed units."""
import json
import subprocess

import pytest

from sdd.llm import AgentError
from sdd.translation import translate_missing


def test_cli_translation_resume_and_receipt_integrity(tmp_cfg, monkeypatch):
    tmp_cfg.agent.kind, tmp_cfg.agent.runner, tmp_cfg.agent.model = 'cli', 'claude', 'fixture-model'
    tmp_cfg.agent.args = ['--effort', 'high']
    tmp_cfg.agent.max_input_chars = 20000
    tmp_cfg.raw['review']['cli_checkpoint'] = True
    tmp_cfg.raw['site'] = dict(translation_batch_size=1)
    calls, interrupted = [], [True]
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])
    def run(argv, **kwargs):
        payload = json.loads(kwargs['prompt'].split('<user>\n', 1)[1].split('\n</user>', 1)[0])
        source = payload['source']
        calls.append(source)
        if source == '둘째 문장' and interrupted[0]:
            raise RuntimeError('controlled CLI interruption')
        raw = json.dumps(dict(text='First sentence' if source == '첫째 문장' else 'Second sentence'))
        return subprocess.CompletedProcess(argv, 0,
            json.dumps(dict(subtype='success', is_error=False, result=raw)), '')
    monkeypatch.setattr('sdd.cli_agent.run', run)
    catalog = dict(strings={'첫째 문장': '', '둘째 문장': ''})
    with pytest.raises(AgentError, match='interruption'):
        translate_missing(tmp_cfg, catalog)
    assert calls == ['첫째 문장', '둘째 문장']
    assert catalog['strings'] == {'첫째 문장': '', '둘째 문장': ''}
    interrupted[0] = False
    result = translate_missing(tmp_cfg, catalog)
    assert calls == ['첫째 문장', '둘째 문장', '둘째 문장']
    assert all(result['strings'].values())
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    resumed = max(runs, key=lambda row: row['started_at'])
    assert resumed['counts']['revalidated'] == 1 and resumed['counts']['completed'] == 1
    checkpoint = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    checkpoint.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='checkpoint'):
        translate_missing(tmp_cfg, catalog)
    assert len(calls) == 3


def test_batched_fresh_calls_obey_budget_and_resume_without_completed_batch(tmp_cfg, monkeypatch):
    from sdd.generation_run import BudgetExceeded
    tmp_cfg.agent.kind, tmp_cfg.agent.runner, tmp_cfg.agent.model = 'cli', 'claude', 'fixture-model'
    tmp_cfg.agent.max_input_chars = 20000
    tmp_cfg.raw['review'].update(cli_checkpoint=True, max_calls=1)
    tmp_cfg.raw['site'] = dict(translation_batch_size=2)
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])
    calls = []
    def run(argv, **kwargs):
        payload = json.loads(kwargs['prompt'].split('<user>\n', 1)[1].split('\n</user>', 1)[0])
        calls.append(list(payload['texts']))
        raw = json.dumps(dict(translations={key: 'Translated '+key for key in payload['texts']}))
        return subprocess.CompletedProcess(argv, 0,
            json.dumps(dict(subtype='success', is_error=False, result=raw)), '')
    monkeypatch.setattr('sdd.cli_agent.run', run)
    catalog = dict(strings={source: '' for source in ('첫째', '둘째', '셋째', '넷째')})
    with pytest.raises(BudgetExceeded):
        translate_missing(tmp_cfg, catalog)
    assert calls == [['0', '1']]
    result = translate_missing(tmp_cfg, catalog)
    assert calls == [['0', '1'], ['2', '3']]
    assert all(result['strings'].values())
