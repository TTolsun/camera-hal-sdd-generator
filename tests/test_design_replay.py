import hashlib
import json

import pytest

from sdd.design_replay import Archive, sha


def archive(tmp_path, cfg, *, raw='actual model answer', tag='page_topic_part_0', user=None):
    cfg.kind, cfg.model = 'ollama', 'local-model'
    request = {'system': 'system', 'user': user or json.dumps({
        'sources': {'src': 'code'}, 'topic': 'question',
        'answer_contract': {'basis': 'implementation', 'required_terms': [['null']]}}),
        'response_schema': {'type': 'object'}}
    receipt = {'http_call': True, 'transport': cfg.kind, 'model': cfg.model,
               'settings': {key: getattr(cfg, key) for key in (
                   'temperature', 'think', 'num_ctx', 'max_output_tokens')},
               'tag': tag, 'request_sha256': sha(request),
               'response_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    (tmp_path / '001.request.json').write_text(json.dumps(request), encoding='utf-8')
    (tmp_path / '001.response.txt').write_bytes(raw.encode())
    (tmp_path / '001.receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    return request, receipt


def test_same_evidence_can_reapply_changed_terms_but_never_changed_question(tmp_cfg, tmp_path):
    request, _ = archive(tmp_path, tmp_cfg.agent)
    store = Archive(tmp_path, tmp_cfg.agent)
    payload = json.loads(request['user'])
    payload['answer_contract']['required_terms'][0].append('널 포인터')
    assert len(list(store.candidates(request['system'], json.dumps(payload), request['response_schema'], 'page_topic_part'))) == 1
    payload['topic'] = 'different question'
    assert not list(store.candidates(request['system'], json.dumps(payload), request['response_schema'], 'page_topic_part'))
    assert not list(store.candidates(request['system'], request['user'], request['response_schema'], 'different_unit'))


@pytest.mark.parametrize('field', ['response', 'model', 'settings', 'length', 'http'])
def test_tampering_and_different_transports_cannot_be_replayed(tmp_cfg, tmp_path, field):
    request, receipt = archive(tmp_path, tmp_cfg.agent)
    if field == 'response':
        (tmp_path / '001.response.txt').write_text('tampered', encoding='utf-8')
        with pytest.raises(ValueError, match='checksum'):
            Archive(tmp_path, tmp_cfg.agent)
        return
    if field == 'model':
        receipt['model'] = 'other'
    elif field == 'settings':
        receipt['settings']['temperature'] = 9
    elif field == 'length':
        receipt['provider'] = {'done_reason': 'length'}
    else:
        receipt['http_call'] = False
    (tmp_path / '001.receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    assert not list(Archive(tmp_path, tmp_cfg.agent).candidates(
        request['system'], request['user'], request['response_schema'], 'page_topic_part'))


def test_review_replay_requires_exact_request_and_otherwise_calls_real_agent(tmp_cfg, tmp_path):
    request, _ = archive(tmp_path, tmp_cfg.agent, user='review request', tag='page_topic_0_grounding')
    class Agent:
        def chat(self, *args, **kwargs):
            return 'new actual review'
    reviewer = Archive(tmp_path, tmp_cfg.agent).reviewer(Agent())
    assert reviewer.chat(request['system'], request['user'], response_schema=request['response_schema']) == 'actual model answer'
    assert reviewer.chat(request['system'], 'changed review', response_schema=request['response_schema']) == 'new actual review'
