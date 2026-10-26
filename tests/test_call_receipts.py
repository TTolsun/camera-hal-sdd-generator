import hashlib
import json
import pytest

from sdd.config import AgentConfig
from sdd.llm import Agent
from sdd.llm import AgentError


def test_http_receipts_survive_retries_and_omit_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('SDD_AGENT_API_KEY', 'secret-fixture')
    calls = []
    def post(self, url, body):
        calls.append(body)
        return {'model': 'qwen-local', 'done_reason': 'stop', 'eval_count': 35,
                'message': {'content': 'generated\nanswer', 'thinking': 'private reasoning'}}
    monkeypatch.setattr(Agent, '_post', post)
    cfg = AgentConfig(kind='ollama', allow_direct_api=True, model='qwen-local')
    for _ in range(2):
        Agent(cfg, tmp_path).chat('source rules', 'source', tag='same', response_schema={'type': 'object'})
    receipts = list(tmp_path.glob('calls/*/*.receipt.json'))
    assert len(calls) == len(receipts) == 2
    for path in receipts:
        data = json.loads(path.read_text())
        assert data['http_call'] and data['transport'] == 'ollama'
        assert data['provider']['eval_count'] == 35
        prefix = path.with_name(path.name.replace('.receipt.json', ''))
        request = json.loads(prefix.with_suffix('.request.json').read_text())
        assert data['request_sha256'] == hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        assert data['response_sha256'] == hashlib.sha256(prefix.with_suffix('.response.txt').read_bytes()).hexdigest()
        assert 'secret-fixture' not in path.read_text() and 'private reasoning' not in path.read_text()


@pytest.mark.parametrize('provider', ['ollama', 'openai-compatible'])
@pytest.mark.parametrize('content', ['', '{"statements": []}'])
def test_truncated_responses_are_archived_but_never_accepted(tmp_path, monkeypatch, provider, content):
    def post(self, url, body):
        if provider == 'ollama':
            return {'message': {'content': content}, 'done_reason': 'length'}
        return {'choices': [{'message': {'content': content}, 'finish_reason': 'length'}]}
    monkeypatch.setattr(Agent, '_post', post)
    with pytest.raises(AgentError, match='출력 토큰 한도'):
        Agent(AgentConfig(kind=provider), tmp_path).chat('rules', 'source')
    receipt = next(tmp_path.glob('calls/*/*.receipt.json'))
    prefix = receipt.with_name(receipt.name.removesuffix('.receipt.json'))
    assert prefix.with_suffix('.response.txt').read_text() == content
