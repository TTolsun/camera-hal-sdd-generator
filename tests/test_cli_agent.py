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
    ('codex', '\n'.join(json.dumps(e) for e in [
        {'type': 'turn.started'},
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'text': '최종 응답'}, ensure_ascii=False)}},
        {'type': 'turn.completed', 'usage': {'output_tokens': 3}}])),
])
def test_cli_stdin_unicode_long_prompt_and_receipt(tmp_path, runner, output, monkeypatch):
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('CLI must not call HTTP'))
    cfg = AgentConfig(runner=runner, command=fake_cli(tmp_path, output), model='chosen/model',
                      args=['--variant', 'approved'], timeout_sec=10, max_input_chars=100000)
    dump = tmp_path / 'prompts'
    user = '공개 입력 $(echo unsafe); `x` & "quotes"\n' * 1400
    schema = {'type': 'object'}
    expected = json.dumps({'text': '최종 응답'}, ensure_ascii=False) if runner == 'codex' else '최종 응답'
    assert Agent(cfg, dump).chat('system rules', user, response_schema=schema) == expected
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
    Agent(cfg, tmp_path / 'prompts').chat('system', 'user')
    captured = json.loads((tmp_path / 'input.json').read_text(encoding='utf-8'))
    assert '--model' not in captured['argv']


def test_claude_native_schema_output_and_receipt_bind_actual_arguments(tmp_path):
    from sdd.call_records import load_record
    from sdd.cli_provenance import verify_cli_receipt
    output = dict(type='result', subtype='success', is_error=False, result='', structured_output={'status': 'ok'})
    cfg = AgentConfig(runner='claude', model='fixture-model', args=['--effort', 'high'],
                      command=fake_cli(tmp_path, json.dumps(output)))
    schema = dict(type='object', required=['status'], properties=dict(status=dict(type='string')))
    dump = tmp_path/'prompts'
    agent = Agent(cfg, dump)
    assert json.loads(agent.chat('system', 'user', response_schema=schema)) == {'status': 'ok'}
    captured = json.loads((tmp_path/'input.json').read_text(encoding='utf-8'))
    index = captured['argv'].index('--json-schema')
    assert json.loads(captured['argv'][index+1]) == schema
    assert captured['argv'][-2:] == ['--effort', 'high']
    record = load_record(agent.last_receipt, root=dump/'calls')
    assert verify_cli_receipt(record.request, record.raw, record.receipt, dump/'calls', cfg)['runner'] == 'claude'


def test_codex_native_schema_and_high_effort_have_receipt_bound_output(tmp_path):
    from sdd.call_records import load_record
    from sdd.cli_provenance import verify_cli_receipt
    schema = dict(type='object', additionalProperties=False, required=['status'], properties=dict(status=dict(type='string')))
    output = '\n'.join(json.dumps(e) for e in [dict(type='thread.started', thread_id='fixture-thread'),
        dict(type='turn.started'), dict(type='item.completed', item=dict(type='agent_message', text='{"status":"ok"}')),
        dict(type='turn.completed', usage=dict(input_tokens=20, output_tokens=5))])
    cmd = fake_cli(tmp_path, output)
    script = Path(cmd[1])
    script.write_text(script.read_text(encoding='utf-8').replace('time.sleep(',
        f"assert json.loads(Path('response-schema.json').read_text(encoding='utf-8')) == {schema!r}\ntime.sleep("), encoding='utf-8')
    cfg = AgentConfig(runner='codex', model='gpt-6.1-terra', args=['-c', 'model_reasoning_effort="high"'], command=cmd)
    dump = tmp_path/'prompts';agent = Agent(cfg, dump)
    assert json.loads(agent.chat('Use supplied sources only.', 'Return status.', response_schema=schema)) == {'status': 'ok'}
    captured = json.loads((tmp_path/'input.json').read_text(encoding='utf-8'))
    assert captured['argv'][:2] == ['exec', '--ignore-user-config']
    assert captured['argv'][-2:] == ['-c', 'model_reasoning_effort="high"']
    assert '--output-schema' in captured['argv'] and '--ephemeral' in captured['argv']
    record = load_record(agent.last_receipt, root=dump/'calls')
    assert record.receipt['provider']['provider']['completion_event'] == 'turn.completed'
    assert verify_cli_receipt(record.request, record.raw, record.receipt, dump/'calls', cfg)['model'] == 'gpt-6.1-terra'
    assert not Path(captured['cwd']).exists()


@pytest.mark.parametrize('events', [
    [dict(type='turn.failed')], [dict(type='error')],
    [dict(type='turn.started'), dict(type='item.completed', item=dict(type='agent_message', text='partial'))],
    [dict(type='turn.started'), dict(type='turn.started')],
    [dict(type='turn.started'), dict(type='item.completed', item=dict(type='command_execution', command='unrequested'))],
    [dict(type='turn.started'), dict(type='turn.completed')],
])
def test_codex_error_tool_use_and_incomplete_turns_cannot_be_success(events):
    from sdd.cli_agent import decode_response
    with pytest.raises(ValueError):
        decode_response('codex', '\n'.join(json.dumps(e) for e in events))


@pytest.mark.parametrize('response', ['{"uniqueItems":["duplicate","duplicate"]}', '{}'])
def test_codex_wire_schema_preserves_properties_and_original_constraints(tmp_path, response):
    from sdd.cli_schema import codex_schema
    schema = dict(type='object', additionalProperties=False, required=['uniqueItems'], properties={
        'uniqueItems': dict(type='array', uniqueItems=True, items=dict(type='string'), minItems=1)})
    wire = codex_schema(schema)
    assert 'uniqueItems' in wire['properties']
    assert 'uniqueItems' not in wire['properties']['uniqueItems']
    assert wire['properties']['uniqueItems']['minItems'] == 1
    assert schema['properties']['uniqueItems']['uniqueItems'] is True
    output = '\n'.join(json.dumps(e) for e in [dict(type='turn.started'),
        dict(type='item.completed', item=dict(type='agent_message', text=response)),
        dict(type='turn.completed')])
    dump = tmp_path/'prompts'
    with pytest.raises(AgentError):
        Agent(AgentConfig(runner='codex', command=fake_cli(tmp_path, output)), dump).chat('s', 'u', response_schema=schema)
    assert list(dump.glob('cli/*.stdout.txt'))
    assert not list(dump.glob('calls/*/*.receipt.json'))


def test_codex_archived_schema_validation_cannot_fetch_remote_references(monkeypatch):
    from sdd.cli_schema import validate_original
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: pytest.fail('No schema network retrieval'))
    with pytest.raises(ValueError, match='original output schema'):
        validate_original('{}', {'$ref': 'https://untrusted.example/remote-schema.json'})


@pytest.mark.parametrize('permanent', [False, True])
@pytest.mark.parametrize('cleanup_error', [PermissionError('fixture retained working directory'), OSError(39, 'directory not empty')])
def test_cli_cleanup_lock_preserves_completed_response_and_records_deferral(tmp_path, monkeypatch, permanent, cleanup_error):
    import shutil
    original = shutil.rmtree
    attempts = []
    def locked(path, *args, **kwargs):
        attempts.append(path)
        if permanent or len(attempts)==1:
            raise cleanup_error
        return original(path, *args, **kwargs)
    monkeypatch.setattr('sdd.cli_agent.shutil.rmtree', locked)
    cfg = AgentConfig(command=fake_cli(tmp_path, 'completed answer'))
    dump = tmp_path/'prompts'
    agent = Agent(cfg, dump)
    assert agent.chat('system','user')=='completed answer'
    receipt=json.loads(agent.last_receipt.read_text(encoding='utf-8'))
    assert receipt['provider']['workspace_cleanup']['status']==('deferred' if permanent else 'removed')
    assert len(list((dump/'calls').rglob('*.receipt.json')))==1
    assert len(attempts)==(5 if permanent else 2)


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX process-group race')
def test_timeout_group_exit_race_keeps_timeout_failure_and_partial_output(monkeypatch):
    from sdd.cli_agent import run
    class Process:
        pid = 42
        attempts = 0
        killed = False
        def communicate(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise subprocess.TimeoutExpired('fixture', 0.1, output=b'partial', stderr=b'diagnostic')
            return '', ''
        def kill(self):
            self.killed = True
    process = Process()
    monkeypatch.setattr('sdd.cli_agent.subprocess.Popen', lambda *a, **kw: process)
    def already_exited(*args):
        raise ProcessLookupError('process group exited')
    monkeypatch.setattr('sdd.cli_agent.os.killpg', already_exited)
    with pytest.raises(RuntimeError, match='초과') as error:
        run(['fixture'], cwd=None, prompt='request', timeout=0.1)
    assert error.value.stdout == b'partial' and error.value.stderr == b'diagnostic'
    assert process.killed and process.attempts == 2


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
        Agent(AgentConfig(command=fake_cli(tmp_path, 'late', delay=30), timeout_sec=0.3),
              tmp_path / 'prompts').chat('s', 'u')


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
