"""The public verifier must reject changed prose even when local hashes are reset."""
import json
from pathlib import Path

import pytest

from replay_fixture import replay_record


@pytest.fixture
def replay(tmp_path):
    return replay_record(tmp_path, 'verify_document_replay.py')


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
    proof['stages']['baseline']['pages']['overview']['expectations'] = [{'topic':'queue-limit','require':['16']}]
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_command_requires_all_eight_pages_and_all_stages(replay):
    module, root, _, _, save = replay
    save()
    with pytest.raises(AssertionError):
        module.verify(root)


def test_recorded_local_qwen_equality_error_is_still_rejected():
    import yaml
    from sdd.answer_contracts import check
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root/'examples/libcamera/fixtures/qwen-document-failures.json').read_text(encoding='utf-8'))
    call = evidence['calls']['pipeline-handler_queue_queue-limit_2']
    assert call['receipt']['transport'] == 'ollama'
    sections = yaml.safe_load((root/'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))['sections']
    page = next(s for s in sections if s['id'] == 'pipeline-requests')
    topic = next(t for t in page['design_topics'] if t['id'] == 'queue')
    rule = next(p['answer_contract'] for p in topic['parts'] if p['id'] == 'capacity')
    with pytest.raises(ValueError, match='비교 연산자'):
        check(rule, json.loads(call['response'])['statements'], 'actual-qwen')


def test_focused_request_preserves_source_bindings(replay):
    module, root, _, proof, save = replay
    old_key, call = next(iter(proof['calls'].items()))
    sources = module.request_sources(call['request']['user'])
    call['request']['user'] = '근거:\n' + json.dumps(sources) + '\n질문: 현재 값은 무엇입니까?'
    receipt = call['receipt']
    receipt['request_sha256'] = module.sha(json.dumps(call['request'], ensure_ascii=False, sort_keys=True))
    key = module.sha(receipt['request_sha256'] + receipt['response_sha256'])
    proof['calls'] = {key: call}
    proof['stages']['baseline']['pages']['overview']['origins']['queue-limit'][0]['call'] = key
    save()
    module.verify(root, complete=False)
