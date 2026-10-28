"""Fake subprocess archives exercise CLI integrity; no model is executed."""
import hashlib
import json
import sys

import pytest

from sdd import cli_agent
from sdd.cli_provenance import verify_cli_receipt
from sdd.config import AgentConfig
from sdd.llm import Agent


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


@pytest.mark.parametrize('tail', [
    {'type': 'step_finish', 'part': {'reason': 'length'}},
    {'type': 'text', 'part': {'text': 'unfinished next step'}},
])
def test_opencode_requires_completion_of_the_final_step(archive, tail):
    args = archive('opencode')
    provider = args['receipt']['provider']
    path = args['calls'].parent / provider['stdout_path']
    raw = path.read_bytes().decode('utf-8') + '\n' + json.dumps(tail)
    path.write_text(raw, encoding='utf-8', newline='\n')
    provider['stdout_sha256'] = digest(raw)
    with pytest.raises(ValueError, match='completion event'):
        cli_agent.decode_response('opencode', raw)
    with pytest.raises(ValueError, match='completed response'):
        verify_cli_receipt(**args)


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('CLI must not call HTTP'))
    monkeypatch.setattr(Agent, '_get', lambda *a: pytest.fail('CLI must not probe HTTP'))

    def create(runner='hermes', model='chosen/model'):
        answer = '{"statements": [{"text": "공개 소스의 응답입니다."}]}'
        if runner == 'claude':
            output = json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                                 'result': answer, 'session_id': 'fake-session'})
        elif runner == 'opencode':
            output = '\n'.join(json.dumps(e) for e in [
                {'type': 'text', 'part': {'text': answer}},
                {'type': 'step_finish', 'sessionID': 'fake-session', 'part': {'reason': 'stop'}},
            ])
        elif runner == 'codex':
            output = '\n'.join(json.dumps(e) for e in [
                {'type': 'turn.started'},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}},
                {'type': 'turn.completed', 'usage': {'output_tokens': 10}},
            ])
        else:
            output = answer
        captured = tmp_path / 'captured-stdin.txt'
        script = tmp_path / 'fake_cli.py'
        script.write_text('import sys\nfrom pathlib import Path\n'
                          f'Path({str(captured)!r}).write_text(sys.stdin.read(), encoding="utf-8", newline="\\n")\n'
                          f'sys.stdout.write({output!r})\n', encoding='utf-8')
        expected = AgentConfig(runner=runner, command=[sys.executable, str(script)], model=model,
                               timeout_sec=10, max_input_chars=10000)
        dump = tmp_path / 'prompts'
        response = Agent(expected, dump).chat('공개 소스 규칙', '공개 소스 질문',
                    response_schema={'type': 'object'}, tag='public-test')
        receipt_path = next(dump.glob('calls/*/*.receipt.json'))
        prefix = receipt_path.with_name(receipt_path.name.removesuffix('.receipt.json'))
        request = json.loads(prefix.with_suffix('.request.json').read_text(encoding='utf-8'))
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        prompt = captured.read_bytes().decode('utf-8')

        def build_prompt(system, user, schema):
            # Use the exact stdin from cli_agent.chat, without copying its assembly.
            assert (system, user, schema) == (request['system'], request['user'], request['response_schema'])
            return prompt

        return dict(request=request, response=response, receipt=receipt, calls=dump / 'calls',
                    expected=expected, build_prompt=build_prompt, decode_stdout=cli_agent.decode_response)

    return create


@pytest.mark.parametrize('runner', ['hermes', 'opencode', 'claude', 'codex'])
@pytest.mark.parametrize('model', ['', 'chosen/model'])
def test_real_agent_archives_from_fake_subprocess_are_verified(archive, runner, model):
    args = archive(runner, model)
    assert args['build_prompt'](args['request']['system'], args['request']['user'],
                                args['request']['response_schema']) == cli_agent.build_prompt(**{
        'system': args['request']['system'], 'user': args['request']['user'],
        'schema': args['request']['response_schema']})
    report = verify_cli_receipt(**args)
    assert report['runner'] == runner and report['model'] == model
    assert report['model_selection'] == ('explicit' if model else 'cli-default')
    assert report['producer'] == f'cli/{runner}/{model or "cli-default"}'
    assert 'human_approval' not in report


@pytest.mark.parametrize('change', ['effort', 'prefix', 'recorded-model'])
def test_configured_cli_arguments_cannot_be_changed_or_relabelled(archive, change):
    args = archive('codex')
    if change == 'effort':
        args['expected'].args = ['-c', 'model_reasoning_effort="high"']
    elif change == 'prefix':
        args['expected'].command.append('different-wrapper-argument')
    else:
        recorded = args['receipt']['provider']['arguments']
        recorded[recorded.index('--model')+1] = 'another-model'
    with pytest.raises(ValueError, match='arguments differ'):
        verify_cli_receipt(**args)


def test_model_only_archive_audit_does_not_claim_argument_profile_verification(archive):
    args = archive('codex')
    args['expected'].command = []
    assert verify_cli_receipt(**args)['arguments_verified'] is False


@pytest.mark.parametrize('field,value', [
    ('schema', True), ('transport', 'response-bundle'), ('cli_call', False), ('http_call', True),
    ('model', 'different/model'), ('request_sha256', 'changed'), ('response_sha256', 'changed'),
])
def test_receipt_marker_identity_and_hash_changes_are_rejected(archive, field, value):
    args = archive()
    args['receipt'][field] = value
    with pytest.raises(ValueError):
        verify_cli_receipt(**args)


@pytest.mark.parametrize('field,value', [
    ('runner', 'claude'), ('model_selection', 'cli-default'), ('exit_code', 2), ('exit_code', False),
    ('prompt_sha256', 'changed'), ('stdout_sha256', 'changed'), ('provider', {'invented': True}),
])
def test_cli_execution_metadata_changes_are_rejected(archive, field, value):
    args = archive()
    args['receipt']['provider'][field] = value
    with pytest.raises(ValueError):
        verify_cli_receipt(**args)


@pytest.mark.parametrize('path', [
    '../outside.stdout.txt', '/absolute.stdout.txt', 'C:/absolute.stdout.txt',
    'cli/../outside.stdout.txt', 'cli/./file.stdout.txt', 'cli//file.stdout.txt',
    'cli\\file.stdout.txt', 'cli/file.stdout.txt:stream', 'other/file.stdout.txt',
])
def test_stdout_paths_cannot_escape_cli_archive(archive, path):
    args = archive()
    args['receipt']['provider']['stdout_path'] = path
    with pytest.raises(ValueError, match='stdout path'):
        verify_cli_receipt(**args)


def test_saved_response_must_match_decoded_stdout_even_with_updated_hash(archive):
    args = archive()
    args['response'] = 'An invented response with its own valid hash.'
    args['receipt']['response_sha256'] = digest(args['response'])
    with pytest.raises(ValueError, match='decoded response'):
        verify_cli_receipt(**args)


def test_raw_stdout_must_match_its_hash_and_decoded_answer(archive):
    args = archive()
    metadata = args['receipt']['provider']
    path = args['calls'].parent / metadata['stdout_path']
    path.write_text('An invented stdout.', encoding='utf-8')
    with pytest.raises(ValueError, match='stdout hash'):
        verify_cli_receipt(**args)
    metadata['stdout_sha256'] = digest('An invented stdout.')
    with pytest.raises(ValueError, match='decoded response'):
        verify_cli_receipt(**args)


def test_request_and_full_cli_prompt_are_both_bound(archive):
    args = archive()
    args['request']['user'] = 'A changed source question.'
    with pytest.raises(ValueError, match='request or response hash'):
        verify_cli_receipt(**args)
    args['receipt']['request_sha256'] = digest(json.dumps(args['request'], ensure_ascii=False, sort_keys=True))
    args['build_prompt'] = lambda *a: 'A different full CLI prompt.'
    with pytest.raises(ValueError, match='prompt hash'):
        verify_cli_receipt(**args)


def test_missing_stdout_is_rejected(archive):
    args = archive()
    path = args['calls'].parent / args['receipt']['provider']['stdout_path']
    path.unlink()
    with pytest.raises(ValueError, match='missing or unreadable'):
        verify_cli_receipt(**args)


def test_incomplete_cli_envelope_cannot_establish_provenance(archive):
    args = archive('opencode')
    metadata = args['receipt']['provider']
    path = args['calls'].parent / metadata['stdout_path']
    partial = json.dumps({'type': 'text', 'part': {'text': args['response']}})
    path.write_text(partial, encoding='utf-8')
    metadata['stdout_sha256'] = digest(partial)
    with pytest.raises(ValueError, match='completed response'):
        verify_cli_receipt(**args)


def test_stdout_symlink_is_rejected_even_when_target_is_inside_archive(archive):
    args = archive()
    path = args['calls'].parent / args['receipt']['provider']['stdout_path']
    target = path.with_name('actual.stdout.txt')
    target.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('This environment does not allow symlink creation')
    with pytest.raises(ValueError, match='Linked CLI stdout'):
        verify_cli_receipt(**args)


def test_stdout_reparse_directory_is_rejected_without_junction_api(archive, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    args = archive()
    target = args['calls'].parent/'cli'
    original = Path.lstat
    def reparse(path, *a, **kw):
        record = original(path, *a, **kw)
        return SimpleNamespace(st_mode=record.st_mode, st_file_attributes=0x400) if path == target else record
    monkeypatch.setattr(Path, 'lstat', reparse)
    monkeypatch.setattr(Path, 'is_junction', lambda self: False, raising=False)
    with pytest.raises(ValueError, match='Linked CLI stdout'):
        verify_cli_receipt(**args)


def test_expected_transport_and_default_model_selection_are_checked(archive):
    args = archive(model='')
    args['receipt']['provider']['model_selection'] = 'explicit'
    with pytest.raises(ValueError, match='identity'):
        verify_cli_receipt(**args)
    args['expected'].kind = 'ollama'
    with pytest.raises(ValueError, match='selected CLI runner'):
        verify_cli_receipt(**args)
