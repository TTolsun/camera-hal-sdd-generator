"""The public verifier must reject changed prose even when local hashes are reset."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def replay(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'examples/libcamera/verify_overview_replay.py'
    spec = importlib.util.spec_from_file_location('overview_replay', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = {'user': 'Question\n' + json.dumps({'reader': 'developer', 'sources': {
        'default': [{'quote_id': 'default:0', 'text': 'unsigned limit = 32;'}]}})}
    raw = {'text': '기본 한도는 32입니다.', 'quote_id': 'default:0', 'covers': ['queue-limit'], 'kind': 'behavior'}
    response = json.dumps({'statements': [raw]})
    receipt = {'transport': 'ollama', 'http_call': True, 'model': 'qwen3.5:9b',
               'tag': 'overview_queue-limit_default_0',
               'request_sha256': module.sha(json.dumps(request, ensure_ascii=False, sort_keys=True)),
               'response_sha256': module.sha(response)}
    key = module.sha(receipt['request_sha256'] + receipt['response_sha256'])
    answer = {k: v for k, v in raw.items() if k != 'quote_id'} | {'evidence': ['default'], 'quote': 'unsigned limit = 32;'}
    artifact = {'body_sha256': module.sha(raw['text']), 'topic_agents': {'queue-limit': 'ollama/qwen3.5:9b'},
                'answers': {'queue-limit': [answer]}}
    proof = {'model': {'name': 'qwen3.5:9b'}, 'calls': {key: {'receipt': receipt, 'request': request, 'response': response}},
             'stages': {'baseline': {'source_commit': 'a' * 40, 'queue_limit': 32, 'pages': {'overview': {
                 'file': 'baseline-overview.md', 'origins': {'queue-limit': [{'call': key, 'index': 0}]}}}}}}

    def save():
        body = artifact['answers']['queue-limit'][0]['text']
        artifact['body_sha256'] = module.sha(body)
        (tmp_path / 'baseline-overview.md').write_text(
            '---\nsource_commit: ' + 'a' * 40 + '\ngenerated_design: ' + json.dumps(artifact, ensure_ascii=False)
            + '\n---\n' + body, encoding='utf-8')
        (tmp_path / 'proof.json').write_text(json.dumps(proof), encoding='utf-8')
    return module, tmp_path, artifact, proof, save


def test_public_verifier_accepts_original_record(replay):
    module, root, _, _, save = replay
    save()
    module.verify(root, complete=False)


def test_public_verifier_rejects_rewritten_prose_with_new_body_hash(replay):
    module, root, artifact, _, save = replay
    artifact['answers']['queue-limit'][0]['text'] = '기본 한도는 32이며 모든 요청의 성공을 보장합니다.'
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_verifier_rejects_fabricated_quote(replay):
    module, root, artifact, _, save = replay
    artifact['answers']['queue-limit'][0]['quote'] = 'unsigned limit = 16;'
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_verifier_rejects_wrong_expected_source_value(replay):
    module, root, _, proof, save = replay
    proof['stages']['baseline']['queue_limit'] = 16
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_command_requires_both_pages_and_all_stages(replay):
    module, root, _, _, save = replay
    save()
    with pytest.raises(AssertionError):
        module.verify(root)
