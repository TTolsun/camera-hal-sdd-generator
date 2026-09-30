import http.client
import json
import subprocess

import pytest
import yaml

from sdd import evaluate
from sdd.facts.model import KnowledgeModel
from sdd.llm import Agent, AgentError


@pytest.fixture
def evaluation_config(tmp_cfg):
    root = tmp_cfg.source_root
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], encoding='utf-8').strip()
    git('init')
    (root / 'camera.cpp').write_text('START\nA request remains owned by its caller.\nEND\n', encoding='utf-8')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    KnowledgeModel(meta={'source_commit': git('rev-parse', 'HEAD')}).save(tmp_cfg.facts_path)
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [{
        'id': 'camera', 'title': 'Camera', 'design_topics': [{
            'id': 'lifetime', 'title': 'Lifetime', 'question': 'Who owns the request?',
            'sources': [{'id': 'owner', 'file': 'camera.cpp', 'start': 'START', 'end': 'END'}]}]}]}), encoding='utf-8')
    path = tmp_cfg.root / 'sdd.yaml'
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
    cfg['agent'].update(kind='openai-compatible', max_input_chars=18000)
    path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    return path


def test_identical_inputs_failures_and_raw_samples_preserved(evaluation_config, tmp_path, monkeypatch):
    prompts = []
    def post(self, url, body):
        prompts.append(body['messages'])
        if body['model'] == 'unavailable':
            raise AgentError('do not publish provider diagnostic')
        return {'choices': [{'message': {'content': '요청 소유권은 호출자에게 있습니다. `camera.cpp:1`'},
                             'finish_reason': 'length'}]}
    monkeypatch.setattr(Agent, '_post', post)
    out = tmp_path / 'experiment'
    result = evaluate.run(evaluation_config, ['baseline', 'unavailable'], ['camera/lifetime'], out, 2)
    assert len(result['samples']) == 4 and len(prompts) == 4
    assert all(p == prompts[0] for p in prompts)
    assert len({s['prompt_sha256'] for s in result['samples']}) == 1
    assert all(not s['verdict']['ok'] for s in result['samples'])
    assert len(list(out.rglob('*.response.md'))) == 2
    assert 'provider diagnostic' not in (out / 'result.json').read_text(encoding='utf-8')
    assert result['human_review'] == 'pending'
    assert not (evaluation_config.parent / 'build/content-review.json').exists()
    assert not (evaluation_config.parent / 'sdd/approvals.json').exists()
    with pytest.raises(ValueError, match='new output'):
        evaluate.run(evaluation_config, ['baseline', 'unavailable'], ['camera/lifetime'], out)


def test_missing_or_omitted_evidence_stops_before_model_call(evaluation_config, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No model calls allowed')
    monkeypatch.setattr(Agent, 'chat', forbidden)
    cfg = yaml.safe_load(evaluation_config.read_text(encoding='utf-8'))
    cfg['agent']['max_input_chars'] = 1
    evaluation_config.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    out = tmp_path / 'experiment'
    with pytest.raises(ValueError, match='Evidence omitted'):
        evaluate.run(evaluation_config, ['a', 'b'], ['camera/lifetime'], out)
    assert not out.exists()
    cfg['agent']['max_input_chars'] = 18000
    evaluation_config.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    sections = evaluation_config.parent / 'config/sections.yaml'
    sections.write_text(sections.read_text(encoding='utf-8').replace('START', 'MISSING'), encoding='utf-8')
    with pytest.raises(ValueError):
        evaluate.run(evaluation_config, ['a', 'b'], ['camera/lifetime'], out)
    assert not out.exists()


def test_changed_prompt_is_rejected(tmp_path, tmp_cfg, monkeypatch):
    monkeypatch.setattr(Agent, 'chat', lambda *a, **kw: 'text')
    agent = evaluate.RecordingAgent(tmp_cfg.agent, tmp_path, {})
    agent.chat('system', 'original', 'case')
    with pytest.raises(ValueError, match='Prompt changed'):
        agent.chat('system', 'modified', 'case')


@pytest.mark.parametrize('error', [TimeoutError('private endpoint'),
                                   ConnectionResetError('private endpoint'),
                                   http.client.IncompleteRead(b'private partial response', 100),
                                   json.JSONDecodeError('bad response', 'private body', 0)])
def test_transport_failure_is_recorded_and_next_candidate_runs(evaluation_config, tmp_path, monkeypatch, error):
    calls = []
    def post(self, url, body):
        calls.append(body['model'])
        if body['model'] == 'failed':
            raise error
        return {'choices': [{'message': {'content': '요청 소유권은 호출자에게 있습니다. `camera.cpp:1`'},
                             'finish_reason': 'stop'}]}
    monkeypatch.setattr(Agent, '_post', post)
    out = tmp_path / 'experiment'
    report = evaluate.run(evaluation_config, ['failed', 'working'], ['camera/lifetime'], out, 1)
    assert calls == ['failed', 'working']
    assert report['samples'][0]['error'] == 'AgentError'
    assert 'error' not in report['samples'][1]
    assert 'private' not in (out / 'result.json').read_text(encoding='utf-8')
    assert len(json.loads((out / 'result.json').read_text(encoding='utf-8'))['samples']) == 2


def test_ollama_discovery_uses_configured_auth_and_timeout(evaluation_config, tmp_path, monkeypatch):
    import urllib.request
    config = yaml.safe_load(evaluation_config.read_text(encoding='utf-8'))
    config['agent'].update(kind='ollama', base_url='https://ollama.example.invalid', timeout_sec=37)
    evaluation_config.write_text(yaml.safe_dump(config), encoding='utf-8')
    monkeypatch.setenv('SDD_AGENT_API_KEY', 'fixture-key')
    observed = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({'models': [{'name': name, 'digest': name} for name in ('a', 'b')]}).encode()
    def urlopen(request, timeout):
        assert isinstance(request, urllib.request.Request)
        observed.append((request.full_url, request.get_header('Authorization'), timeout))
        return Response()
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(Agent, '_post', lambda *a: {'message': {'content': '완료했습니다.'}, 'done_reason': 'stop'})
    out = tmp_path / 'experiment'
    evaluate.run(evaluation_config, ['a', 'b'], ['camera/lifetime'], out, 1)
    assert observed == [('https://ollama.example.invalid/api/tags', 'Bearer fixture-key', 37)]
    assert 'fixture-key' not in (out / 'result.json').read_text(encoding='utf-8')


def test_archive_write_failure_stops_comparison(evaluation_config, tmp_path, monkeypatch):
    calls = []
    def post(self, url, body):
        calls.append(body['model'])
        return {'choices': [{'message': {'content': 'response'}, 'finish_reason': 'stop'}]}
    monkeypatch.setattr(Agent, '_post', post)
    original = evaluate.write_json
    def write(path, value):
        if path.name == 'transport-response.json':
            raise PermissionError('archive unavailable')
        return original(path, value)
    monkeypatch.setattr(evaluate, 'write_json', write)
    with pytest.raises(PermissionError, match='archive unavailable'):
        evaluate.run(evaluation_config, ['a', 'b'], ['camera/lifetime'], tmp_path / 'experiment', 1)
    assert calls == ['a']
