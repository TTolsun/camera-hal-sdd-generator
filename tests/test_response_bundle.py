import json
from pathlib import Path

import pytest

from sdd.config import AgentConfig
from sdd.llm import Agent, AgentError


def test_bundle_binds_prompt_schema_and_model(tmp_path):
    agent = Agent(AgentConfig(kind='response-bundle', model='external-llm', response_dir=str(tmp_path)))
    schema = {'type': 'object'}
    with pytest.raises(AgentError, match='현재 입력'):
        agent.chat('system', 'source', response_schema=schema)
    request_path = next(tmp_path.glob('*.request.json'))
    request = json.loads(request_path.read_text(encoding='utf-8'))
    envelope = {k: request[k] for k in ('schema', 'model', 'request_sha256')}
    response_path = request_path.with_name(request_path.name.replace('.request.', '.response.'))
    response_path.write_text(json.dumps(envelope | {'response': '{"statements": []}'}), encoding='utf-8')
    assert agent.chat('system', 'source', response_schema=schema) == '{"statements": []}'
    for system, user, shape in [('new system', 'source', schema), ('system', 'changed source', schema), ('system', 'source', None)]:
        with pytest.raises(AgentError, match='현재 입력'):
            agent.chat(system, user, response_schema=shape)
    for field, value in [('model', 'other'), ('request_sha256', 'wrong'), ('schema', 99), ('response', '')]:
        response_path.write_text(json.dumps(envelope | {'response': 'text'} | {field: value}), encoding='utf-8')
        with pytest.raises(AgentError, match='응답 파일'):
            agent.chat('system', 'source', response_schema=schema)


def test_exact_excerpt_names_do_not_forge_structural_facts():
    from sdd.facts.model import KnowledgeModel
    from sdd.semantic import review
    model = KnowledgeModel()
    text = '`std::shared_ptr`로 수명을 관리합니다 `a.cpp:1`.'
    assert review(text, model, {'a.cpp:1'})
    assert not review(text, model, {'a.cpp:1'}, source_identifiers={'std::shared_ptr'})
    assert review(text.replace('std::shared_ptr', 'madeup::Pointer'), model, {'a.cpp:1'}, source_identifiers={'std::shared_ptr'})
