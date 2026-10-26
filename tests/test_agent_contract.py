"""Agent adapters preserve the small chat port's optional response schema."""
import inspect

from sdd.config import AgentConfig
from sdd.evaluate import RecordingAgent
from sdd.llm import Agent


def test_recording_agent_forwards_response_schema(tmp_path, monkeypatch):
    received = []
    schema = {'type': 'object', 'required': ['answer']}

    def chat(self, system, user, tag='prompt', response_schema=None):
        received.append((system, user, tag, response_schema))
        return 'recorded response'

    monkeypatch.setattr(Agent, 'chat', chat)
    agent = RecordingAgent(AgentConfig(), tmp_path, {})
    inspect.signature(agent.chat).bind('system', 'user', response_schema=schema)
    assert agent.chat('system', 'user', tag='case', response_schema=schema) == 'recorded response'
    assert received == [('system', 'user', 'case', schema)]
