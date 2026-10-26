import copy
import json
from pathlib import Path

import pytest

from sdd.config import AgentConfig
from sdd.llm import Agent
from sdd.repair_reader import import_calls, repair, digest


@pytest.fixture
def recorded(tmp_path):
    cfg = AgentConfig(kind='ollama', allow_direct_api=True, model='test-model')
    seed = tmp_path / 'seed'
    agent = Agent(cfg, seed / 'prompts')
    # Synthetic transport response for provenance unit tests, never an eval.
    agent._post = lambda *_: {'message': {'content': 'recorded model text'}, 'done': True}
    agent.chat('current policy', 'current source and question', tag='page_topic_part_0')
    return seed, cfg


def test_replay_preserves_origin_and_explicitly_records_non_http_transport(tmp_path, recorded):
    seed, cfg = recorded
    origins, bundle = tmp_path / 'origins', tmp_path / 'bundle'
    assert import_calls(seed, cfg, origins, bundle) == 1
    replay_cfg = copy.deepcopy(cfg)
    replay_cfg.kind, replay_cfg.response_dir = 'response-bundle', str(bundle)
    replay = Agent(replay_cfg, tmp_path / 'replay')
    assert replay.chat('current policy', 'current source and question') == 'recorded model text'
    original = json.loads(next(origins.rglob('*.receipt.json')).read_text(encoding='utf-8'))
    repeated = json.loads(next((tmp_path / 'replay/calls').rglob('*.receipt.json')).read_text(encoding='utf-8'))
    assert original['http_call'] is True and repeated['http_call'] is False
    assert original['request_sha256'] == repeated['request_sha256']
    assert original['response_sha256'] == repeated['response_sha256']
    with pytest.raises(RuntimeError, match='현재 입력'):
        replay.chat('current policy', 'a changed source or question')


@pytest.mark.parametrize('damage', ['response', 'request', 'model', 'settings', 'non-http'])
def test_unverifiable_seed_fails_before_any_import(tmp_path, recorded, damage):
    seed, cfg = recorded
    if damage in ('request', 'response'):
        suffix = '.request.json' if damage == 'request' else '.response.txt'
        path = next((seed/'prompts/calls').rglob('*' + suffix))
        if damage == 'request':
            data = json.loads(path.read_text(encoding='utf-8')); data['user'] = 'changed question'
            path.write_text(json.dumps(data), encoding='utf-8')
        else:
            path.write_text('manually rewritten answer', encoding='utf-8')
    elif damage == 'model':
        cfg.model = 'another-model'
    elif damage == 'settings':
        cfg.temperature += 0.5
    else:
        path = next((seed/'prompts/calls').rglob('*.receipt.json'))
        data = json.loads(path.read_text(encoding='utf-8')); data['http_call'] = False
        path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='mismatch'):
        import_calls(seed, cfg, tmp_path/'origins', tmp_path/'bundle')
    assert not (tmp_path/'origins').exists() and not (tmp_path/'bundle').exists()


def test_conflicting_valid_receipts_are_not_silently_selected(tmp_path, recorded):
    seed, cfg = recorded
    receipt_path = next((seed/'prompts/calls').rglob('*.receipt.json'))
    prefix = str(receipt_path).removesuffix('.receipt.json')
    request = json.loads(Path(prefix+'.request.json').read_text(encoding='utf-8'))
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    receipt['response_sha256'] = digest('different valid response')
    (receipt_path.parent/'999.request.json').write_text(json.dumps(request), encoding='utf-8')
    (receipt_path.parent/'999.response.txt').write_text('different valid response', encoding='utf-8')
    (receipt_path.parent/'999.receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='Conflicting'):
        import_calls(seed, cfg, tmp_path/'origins', tmp_path/'bundle')
    assert not (tmp_path/'origins').exists()


def test_repair_rejects_source_change_and_existing_output_before_calls(tmp_cfg, tmp_path):
    from sdd.facts.model import KnowledgeModel
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.sections_file.write_text('sections:\n- id: page\n  design_generation: llm\n', encoding='utf-8')
    KnowledgeModel(meta={'source_commit': 'a'*40}).save(tmp_cfg.facts_path)
    seed = tmp_path/'seed'; seed.mkdir()
    (seed/'evaluation.json').write_text(json.dumps({'source_commit': 'b'*40}), encoding='utf-8')
    output = tmp_path/'repair'
    with pytest.raises(ValueError, match='same source commit'):
        repair(tmp_cfg, seed, ['page'], output)
    assert not output.exists()
    output.mkdir(); (output/'keep.txt').write_text('original', encoding='utf-8')
    with pytest.raises(ValueError, match='new isolated'):
        repair(tmp_cfg, seed, ['page'], output)
    assert (output/'keep.txt').read_text(encoding='utf-8') == 'original'
