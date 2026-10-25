"""Provenance must survive neither rewritten prose nor forged transport claims."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('vendor_trial_proof',
    Path(__file__).parents[1] / 'examples/libcamera/verify_vendor_trial.py')
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def fixture(root, *, changed_prose=False, http=True):
    settings = dict(temperature=0.1, think=False, num_ctx=16384, max_output_tokens=6000)
    statement = dict(text='호출자는 완료까지 버퍼를 유지해야 합니다.', quote_id='source:0',
                     covers=['lifetime'], kind='behavior')
    quote = 'The caller shall retain the buffer until completion.'
    request = dict(system='Use the source.', user=json.dumps(dict(reader='Vendor',
        sources={'source': [dict(text=quote, quote_id='source:0')]}), ensure_ascii=False), response_schema={})
    response = json.dumps(dict(statements=[statement]), ensure_ascii=False)
    receipt = dict(http_call=http, transport='ollama', model='local-test', settings=settings,
                   tag='page_lifetime_buffer_0', request_sha256=proof.digest(json.dumps(request, ensure_ascii=False, sort_keys=True)),
                   response_sha256=proof.digest(response))
    save(root/'calls/1.receipt.json', receipt)
    save(root/'calls/1.request.json', request)
    (root/'calls/1.response.txt').write_text(response, encoding='utf-8')
    answer = {k: v for k, v in statement.items() if k != 'quote_id'}
    answer.update(evidence=['source'], quote=quote, part_id='buffer')
    if changed_prose:
        answer['text'] = '라이브러리는 버퍼 수명을 보장합니다.'
    body = answer['text']
    artifact = dict(answers={'lifetime': [answer]}, topic_agents={'lifetime': 'ollama/local-test'},
                    body_sha256=proof.digest(body))
    document = '---\nsource_commit: ' + 'a'*40 + '\ngenerated_design: ' + json.dumps(artifact, ensure_ascii=False) + '\n---\n' + body
    path = root/'manuscripts/page.md'
    path.parent.mkdir()
    path.write_text(document, encoding='utf-8')
    (root/'sections.yaml').write_text('sections: []', encoding='utf-8')
    save(root/'evaluation.json', dict(publishable=False, human_approval='pending', provider='ollama', model='local-test',
        source_commit='a'*40, settings=settings, sections_sha256=hashlib.sha256((root/'sections.yaml').read_bytes()).hexdigest(),
        results=[dict(section='page', automatic_checks='passed', manuscripts=[dict(path='manuscripts/page.md',
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())])]))


def test_unmodified_answer_has_http_provenance_without_semantic_approval(tmp_path):
    fixture(tmp_path)
    result = proof.verify(tmp_path)
    assert result['answers'] == result['http_calls'] == 1
    assert result['semantic_approval'] is False and result['human_approval'] is False


@pytest.mark.parametrize('changes', [dict(changed_prose=True), dict(http=False)])
def test_rehashed_manual_rewrite_or_non_http_origin_is_not_model_success(tmp_path, changes):
    fixture(tmp_path, **changes)
    with pytest.raises(AssertionError):
        proof.verify(tmp_path)
