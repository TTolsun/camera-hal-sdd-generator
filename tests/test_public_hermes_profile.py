"""Public CLI settings are explicit and do not constrain internal deployments."""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from sdd import hermes_review, idle_review
from sdd.config import AgentConfig, load
from sdd.llm import Agent
from test_hermes_review import review_case


PUBLIC_CONFIG = Path(__file__).resolve().parents[1] / 'examples/libcamera/sdd.yaml'


@pytest.fixture
def public_config(tmp_path):
    path = tmp_path / 'sdd.yaml'
    path.write_bytes(PUBLIC_CONFIG.read_bytes())
    return path


def _capture_cli(tmp_path, monkeypatch, agent):
    """Execute a local CLI stand-in, without a model or network call."""
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('No direct API'))
    monkeypatch.setattr(Agent, '_get', lambda *a: pytest.fail('No direct API probe'))
    outputs = {
        'hermes': 'answer',
        'claude': json.dumps({'subtype': 'success', 'result': 'answer'}),
        'opencode': '\n'.join(json.dumps(e) for e in [
            {'type': 'text', 'part': {'text': 'answer'}},
            {'type': 'step_finish', 'part': {'reason': 'stop'}}]),
    }
    script = tmp_path / 'selected_cli.py'
    captured = tmp_path / 'argv.json'
    script.write_text(
        'import json,sys\nfrom pathlib import Path\n'
        'sys.stdin.read()\n'
        f'Path({str(captured)!r}).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")\n'
        f'print({outputs[agent.runner]!r})\n', encoding='utf-8')
    configured = replace(agent, command=[sys.executable, str(script)])
    assert Agent(configured, tmp_path / 'records').chat('system', 'user') == 'answer'
    return json.loads(captured.read_text(encoding='utf-8'))


def test_public_profile_reaches_hermes_cli(public_config, tmp_path, monkeypatch):
    cfg = load(public_config)
    assert (cfg.agent.kind, cfg.agent.runner) == ('cli', 'hermes')
    assert not {'num_ctx', 'think', 'max_output_tokens'} & cfg.raw['agent'].keys()
    argv = _capture_cli(tmp_path, monkeypatch, cfg.agent)
    assert argv == ['chat', '--ignore-rules', '--toolsets', 'todo', '--max-turns', '4',
                    '-Q', '--query-file', '-', '--model', 'qwen3.5:9b-ctx64k',
                    '--provider', 'custom', '--reasoning', 'high']


@pytest.mark.parametrize('selection', ['local', 'explicit'])
def test_internal_model_provider_and_effort_are_replaceable(public_config, tmp_path, monkeypatch, selection):
    settings = {'model': 'internal-approved-model',
                'args': ['--provider', 'internal-provider', '--reasoning', 'medium']}
    if selection == 'local':
        public_config.with_name('sdd.local.yaml').write_text(
            yaml.safe_dump({'agent': settings}), encoding='utf-8')
        agent = load(public_config).agent
    else:
        agent = replace(load(public_config).agent, **settings)
    argv = _capture_cli(tmp_path, monkeypatch, agent)
    assert argv[-6:] == ['--model', 'internal-approved-model', '--provider',
                         'internal-provider', '--reasoning', 'medium']
    assert 'qwen3.5:9b-ctx64k' not in argv


@pytest.mark.parametrize('runner,args,prefix', [
    ('opencode', ['--variant', 'approved'], ['run', '--format', 'json']),
    ('claude', ['--effort', 'medium'], ['--print', '--output-format', 'json']),
])
def test_selected_runner_has_independent_arguments(public_config, tmp_path, monkeypatch, runner, args, prefix):
    public_config.with_name('sdd.local.yaml').write_text(yaml.safe_dump({'agent': {
        'runner': runner, 'model': 'internal/selected', 'args': args}}), encoding='utf-8')
    argv = _capture_cli(tmp_path, monkeypatch, load(public_config).agent)
    assert argv[:len(prefix)] == prefix
    assert argv[-4:] == ['--model', 'internal/selected', *args]
    assert not {'hermes', '--reasoning', '--provider', 'qwen3.5:9b-ctx64k'} & set(argv)


def test_general_default_keeps_cli_model_configuration(tmp_path, monkeypatch):
    path = tmp_path / 'sdd.yaml'
    path.write_text('{}', encoding='utf-8')
    cfg = load(path).agent
    assert cfg == AgentConfig()
    argv = _capture_cli(tmp_path, monkeypatch, cfg)
    assert not {'--model', '--provider', '--reasoning'} & set(argv)


@pytest.mark.parametrize('command', [None, ['custom-hermes', '--reasoning', 'low', '-z', '{prompt}']])
def test_legacy_idle_default_and_command_override(tmp_cfg, tmp_path, monkeypatch, command):
    tmp_cfg.agent.kind = 'dry-run'
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"kind":"no_gap"}', '')
    monkeypatch.setattr(idle_review.subprocess, 'run', run)
    assert idle_review._ask(tmp_cfg, 'prompt', {} if command is None else {'command': command}, tmp_path) == {'kind': 'no_gap'}
    expected = ['hermes', '--ignore-rules', '--toolsets', 'todo', '--reasoning', 'high', '-z', 'prompt']
    assert calls == [expected if command is None else [a.replace('{prompt}', 'prompt') for a in command]]


def test_legacy_changed_source_review_default_effort(review_case, monkeypatch):
    cfg, model, report = review_case
    cfg.agent.kind = 'dry-run'
    calls = []
    original_run = subprocess.run
    def run(argv, **kwargs):
        if argv[0] == 'hermes':
            calls.append(argv)
            response = {'reason': 'The contract changed.', 'statements': [
                {'text': '새 계약입니다.', 'covers': ['contract'], 'evidence': ['api']}]}
            return subprocess.CompletedProcess(argv, 0, json.dumps(response), '')
        return original_run(argv, **kwargs)
    monkeypatch.setattr(hermes_review.subprocess, 'run', run)
    hermes_review.revise(cfg, model, report, {})
    assert len(calls) == 1
    assert calls[0][:7] == ['hermes', '--ignore-rules', '--toolsets', 'todo', '--reasoning', 'high', '-z']
    assert '--model' not in calls[0]
