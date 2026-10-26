import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from sdd.config import AgentConfig, load
from sdd.llm import Agent, AgentError


def test_default_and_local_runner_selection(tmp_path):
    path = tmp_path / 'sdd.yaml'
    path.write_text('{}', encoding='utf-8')
    cfg = load(path).agent
    assert (cfg.kind, cfg.runner, cfg.model, cfg.allow_direct_api) == ('cli', 'hermes', '', False)
    path.with_name('sdd.local.yaml').write_text('agent: {runner: claude, model: approved-model}', encoding='utf-8')
    cfg = load(path).agent
    assert (cfg.kind, cfg.runner, cfg.model) == ('cli', 'claude', 'approved-model')


@pytest.mark.parametrize('agent', [{'runner': 'unknown'}, {'command': 'hermes -z'},
                                  {'args': [None]}, {'allow_direct_api': 'false'}])
def test_invalid_cli_config_is_rejected(tmp_path, agent):
    path = tmp_path / 'sdd.yaml'
    path.write_text(yaml.safe_dump({'agent': agent}), encoding='utf-8')
    with pytest.raises(ValueError):
        load(path)


@pytest.mark.parametrize('kind', ['ollama', 'openai-compatible'])
def test_direct_api_requires_explicit_opt_in(kind, monkeypatch):
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('Direct API must not be called'))
    monkeypatch.setattr(Agent, '_get', lambda *a: pytest.fail('Direct API must not be probed'))
    agent = Agent(AgentConfig(kind=kind))
    with pytest.raises(AgentError, match='비활성화'):
        agent.chat('system', 'user')
    with pytest.raises(AgentError, match='비활성화'):
        agent.ping()


def fake_cli(tmp_path, output, *, code=0, delay=0):
    path = tmp_path / 'fake_cli.py'
    path.write_text('import json,sys,time,os\nfrom pathlib import Path\n'
                    'prompt=sys.stdin.read()\n'
                    f'Path({str(tmp_path / "input.json")!r}).write_text(json.dumps(dict(prompt=prompt,argv=sys.argv[1:],cwd=os.getcwd())),encoding="utf-8")\n'
                    f'time.sleep({delay!r})\nprint({output!r})\nsys.exit({code})\n', encoding='utf-8')
    return [sys.executable, str(path)]


@pytest.mark.parametrize('runner,output', [
    ('hermes', '최종 응답'),
    ('claude', json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': '최종 응답'})),
    ('opencode', '\n'.join(json.dumps(e) for e in [
        {'type': 'text', 'part': {'text': '최종 응답'}},
        {'type': 'step_finish', 'part': {'reason': 'stop'}}])),
])
def test_cli_stdin_unicode_long_prompt_and_receipt(tmp_path, runner, output, monkeypatch):
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('CLI must not call HTTP'))
    cfg = AgentConfig(runner=runner, command=fake_cli(tmp_path, output), model='chosen/model',
                      args=['--variant', 'approved'], timeout_sec=10, max_input_chars=100000)
    dump = tmp_path / 'prompts'
    user = '공개 입력 $(echo unsafe); `x` & "quotes"\n' * 1400
    schema = {'type': 'object'}
    assert Agent(cfg, dump).chat('system rules', user, response_schema=schema) == '최종 응답'
    captured = json.loads((tmp_path / 'input.json').read_text(encoding='utf-8'))
    assert user in captured['prompt'] and json.dumps(schema) in captured['prompt']
    assert user not in captured['argv']
    assert captured['argv'][-4:] == ['--model', 'chosen/model', '--variant', 'approved']
    assert not Path(captured['cwd']).exists()  # Empty per-call workspace is removed.
    receipt = json.loads(next(dump.glob('calls/*/*.receipt.json')).read_text(encoding='utf-8'))
    assert receipt['cli_call'] is True and receipt['http_call'] is False
    assert receipt['provider']['runner'] == runner
    assert receipt['provider']['model_selection'] == 'explicit'
    assert (dump / receipt['provider']['stdout_path']).exists()


def test_cli_default_model_is_not_overridden(tmp_path):
    cfg = AgentConfig(command=fake_cli(tmp_path, 'answer'))
    Agent(cfg).chat('system', 'user')
    captured = json.loads((tmp_path / 'input.json').read_text(encoding='utf-8'))
    assert '--model' not in captured['argv']


def test_missing_cli_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('No API fallback'))
    with pytest.raises(AgentError, match='찾지 못했습니다'):
        Agent(AgentConfig(runner='opencode', command=['sdd-nonexistent-cli'])).chat('s', 'u')


@pytest.mark.parametrize('runner,output,code', [
    ('hermes', 'partial answer', 2), ('hermes', '', 0), ('claude', '{"is_error":true}', 0),
    ('claude', 'not JSON', 0), ('opencode', '{"type":"error"}', 0),
    ('opencode', '{"type":"text","part":{"text":"partial"}}', 0),
])
def test_cli_failures_preserve_raw_output_without_success_receipt(tmp_path, runner, output, code):
    dump = tmp_path / 'prompts'
    with pytest.raises(AgentError):
        Agent(AgentConfig(runner=runner, command=fake_cli(tmp_path, output, code=code)), dump).chat('s', 'u')
    assert list(dump.glob('cli/*.stdout.txt'))
    assert not list(dump.glob('calls/*/*.receipt.json'))


def test_cli_timeout_stops_instead_of_using_another_runner(tmp_path):
    with pytest.raises(AgentError, match='초과'):
        Agent(AgentConfig(command=fake_cli(tmp_path, 'late', delay=30), timeout_sec=0.3)).chat('s', 'u')


def test_automation_uses_selected_cli(tmp_cfg, tmp_path, monkeypatch):
    from sdd.idle_review import _ask
    tmp_cfg.agent = AgentConfig(runner='claude')
    calls = []
    def chat(self, system, user, **kwargs):
        calls.append(self.cfg.runner)
        return '{"status":"deferred"}'
    monkeypatch.setattr(Agent, 'chat', chat)
    assert _ask(tmp_cfg, 'public prompt', {}, tmp_path) == {'status': 'deferred'}
    assert calls == ['claude']


def test_cli_budget_includes_schema(tmp_path):
    cfg = AgentConfig(command=fake_cli(tmp_path, 'answer'), max_input_chars=300)
    with pytest.raises(AgentError, match='입력 한도'):
        Agent(cfg).chat('s', 'u', response_schema={'description': 'x'*400})
    assert not (tmp_path / 'input.json').exists()


def test_cli_rejects_legacy_automation_command(tmp_cfg, tmp_path):
    from sdd.idle_review import _ask
    tmp_cfg.agent.kind = 'cli'
    with pytest.raises(ValueError, match='agent.command'):
        _ask(tmp_cfg, 'prompt', {'command': ['hermes']}, tmp_path)
