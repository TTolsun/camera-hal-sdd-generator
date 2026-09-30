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
