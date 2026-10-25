import hashlib
import json

import pytest

from sdd.facts.model import KnowledgeModel
from sdd.provenance import verify_calls


def setup(tmp_path):
    model = KnowledgeModel()
    root = tmp_path / 'calls'
    root.mkdir()
    manuscripts = tmp_path / 'manuscripts'
    manuscripts.mkdir()
    source = 'void stop() { cancelPending(); }'
    statement = dict(text='stop()은 대기 요청 취소 함수를 호출합니다.', quote_id='code:0',
                     kind='behavior', covers=['shutdown'])
    request = {'system': 'grounded prose', 'user': 'Answer: ' + json.dumps({
        'sources': {'code': [{'text': source, 'quote_id': 'code:0'}]}}), 'response_schema': {}}
    raw = json.dumps({'statements': [statement]}, ensure_ascii=False)
    receipt = {'tag': 'device_stop_0', 'http_call': True, 'transport': 'ollama', 'model': 'test',
               'request_sha256': hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
               'response_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    (root / '001.request.json').write_text(json.dumps(request), encoding='utf-8')
    (root / '001.response.txt').write_text(raw, encoding='utf-8')
    (root / '001.receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    answer = {k: v for k, v in statement.items() if k != 'quote_id'} | {'quote': source, 'evidence': ['code']}
    artifact = {'answers': {'stop': [answer]}, 'reused_topics': []}
    page = manuscripts / 'device.md'
    def save():
        page.write_text('---\nsection: device\ngenerated_design: ' + json.dumps(artifact, ensure_ascii=False)
                        + '\n---\n# Device\n', encoding='utf-8')
    save()
    return model, manuscripts, root, artifact, save


def test_model_authorship_matches_exact_saved_response(tmp_path):
    model, manuscripts, calls, artifact, save = setup(tmp_path)
    report = verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')
    assert report['documents'] == report['topics'] == report['statements'] == 1
    artifact['answers']['stop'][0]['text'] += ' 원응답에 없는 새 설명입니다.'
    save()
    with pytest.raises(ValueError, match='No matching HTTP'):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')


@pytest.mark.parametrize('change', ['response', 'provider', 'reuse'])
def test_tampered_or_imported_responses_cannot_establish_authorship(tmp_path, change):
    model, manuscripts, calls, artifact, save = setup(tmp_path)
    if change == 'response':
        (calls / '001.response.txt').write_text('different response', encoding='utf-8')
    elif change == 'provider':
        path = calls / '001.receipt.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['http_call'] = False
        path.write_text(json.dumps(data), encoding='utf-8')
    else:
        artifact['reused_topics'] = ['stop']
        save()
    with pytest.raises(ValueError):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')


def test_part_identity_must_match_real_call_tag(tmp_path):
    model, manuscripts, calls, artifact, save = setup(tmp_path)
    artifact['answers']['stop'][0]['part_id'] = 'cancel'
    receipt_path = calls / '001.receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['tag'] = 'device_stop_cancel_0'
    receipt_path.write_text(json.dumps(receipt))
    save()
    assert verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')['statements'] == 1
    artifact['answers']['stop'][0]['part_id'] = 'different'
    save()
    with pytest.raises(ValueError, match='No matching HTTP'):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')


def test_partial_json_is_not_provenance_even_when_parseable(tmp_path):
    model, manuscripts, calls, artifact, save = setup(tmp_path)
    path = calls / '001.receipt.json'
    receipt = json.loads(path.read_text())
    receipt['provider'] = {'done_reason': 'length'}
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='No matching HTTP'):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')


def test_visual_draft_requires_same_real_http_response_and_model(tmp_path):
    model, manuscripts, calls, artifact, save = setup(tmp_path)
    draft = {'nodes': [{'id': 'start'}], 'edges': []}
    request = {'system': 'visual', 'user': '{}', 'response_schema': {}}
    raw = json.dumps(draft)
    receipt = {'tag': 'visual_device_flow_0', 'http_call': True, 'transport': 'ollama', 'model': 'test',
               'request_sha256': hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
               'response_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    (calls / '002.request.json').write_text(json.dumps(request), encoding='utf-8')
    (calls / '002.response.txt').write_text(raw, encoding='utf-8')
    (calls / '002.receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    page = manuscripts / 'visual-only.md'
    record = {'producer': 'ollama/test', 'draft': draft, 'reused': False}
    def save_visual():
        page.write_text('---\nsection: device\ngenerated_visuals: ' + json.dumps({'records': {'flow': record}})
                        + '\n---\n# Visual\n', encoding='utf-8')
    save_visual()
    assert verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')['visuals'] == 1
    record['draft'] = {'nodes': [{'id': 'invented'}], 'edges': []}
    save_visual()
    with pytest.raises(ValueError, match='No matching HTTP visual'):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')
