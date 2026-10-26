"""Record integrity is independent of HTTP/CLI identity and reuse policy."""
import hashlib
import json
from pathlib import Path

import pytest

from sdd.call_records import canonical_request_hash, iter_records, load_record


def record(root, name='001', *, raw='한글\r\nsecond line\n', transport='cli'):
    root.mkdir(parents=True, exist_ok=True)
    request = {'system': '규칙', 'user': '질문', 'response_schema': {'type': 'object'}}
    receipt = {'request_sha256': canonical_request_hash(request),
               'response_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
               'transport': transport, 'http_call': False, 'cli_call': True,
               'provider': {'finish_reason': 'length'}, 'model': 'model/any', 'settings': {}}
    path = root / (name + '.receipt.json')
    path.write_text(json.dumps(receipt), encoding='utf-8')
    path.with_name(name + '.request.json').write_text(json.dumps(request, indent=3), encoding='utf-8')
    path.with_name(name + '.response.txt').write_bytes(raw.encode('utf-8'))
    return path, receipt, request, raw


def test_loader_preserves_raw_bytes_and_does_not_apply_transport_or_completion_policy(tmp_path):
    path, receipt, request, raw = record(tmp_path)
    loaded = load_record(path, root=tmp_path)
    assert loaded.receipt == receipt and loaded.request == request and loaded.raw == raw
    assert loaded.receipt_path == path
    assert loaded.request_path == path.with_name('001.request.json')
    assert loaded.response_path == path.with_name('001.response.txt')
    assert load_record(path) == loaded


def test_canonical_hash_ignores_json_order_and_spacing_but_keeps_request_fields():
    first = {'system': '한글', 'user': '질문', 'response_schema': None}
    reordered = {'response_schema': None, 'user': '질문', 'system': '한글'}
    assert canonical_request_hash(first) == canonical_request_hash(reordered)
    assert canonical_request_hash(first) != canonical_request_hash({**first, 'user': '다른 질문'})
    assert canonical_request_hash(first) != canonical_request_hash({'system': '한글', 'user': '질문'})


@pytest.mark.parametrize('changed', ['receipt-request-hash', 'receipt-response-hash', 'request', 'response', 'newline'])
def test_loader_rejects_tampering_and_newline_normalization(tmp_path, changed):
    path, receipt, request, raw = record(tmp_path)
    if changed == 'receipt-request-hash':
        receipt['request_sha256'] = '0' * 64
    elif changed == 'receipt-response-hash':
        receipt['response_sha256'] = '0' * 64
    elif changed == 'request':
        request['user'] = 'altered question'
        path.with_name('001.request.json').write_text(json.dumps(request), encoding='utf-8')
    else:
        raw = raw.replace('\r\n', '\n') if changed == 'newline' else raw + 'altered'
        path.with_name('001.response.txt').write_bytes(raw.encode('utf-8'))
    path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='checksum mismatch'):
        load_record(path, root=tmp_path)


@pytest.mark.parametrize('missing', ['request.json', 'response.txt'])
def test_loader_rejects_incomplete_triplet(tmp_path, missing):
    path, _, _, _ = record(tmp_path)
    path.with_name('001.' + missing).unlink()
    with pytest.raises(FileNotFoundError):
        load_record(path, root=tmp_path)


@pytest.mark.parametrize('target,value', [('receipt', []), ('request', 'not an object')])
def test_loader_requires_json_objects(tmp_path, target, value):
    path, _, _, _ = record(tmp_path)
    destination = path if target == 'receipt' else path.with_name('001.request.json')
    destination.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='JSON objects'):
        load_record(path, root=tmp_path)


def test_iterator_does_not_resolve_conflicting_or_different_transport_responses(tmp_path):
    first, _, _, _ = record(tmp_path / 'a', raw='first', transport='cli')
    second, _, _, _ = record(tmp_path / 'b', raw='conflicting', transport='response-bundle')
    records = list(iter_records(tmp_path))
    assert [r.receipt_path for r in records] == [first, second]
    assert [r.raw for r in records] == ['first', 'conflicting']


def test_loader_rejects_receipt_outside_root_and_wrong_suffix(tmp_path):
    path, _, _, _ = record(tmp_path / 'calls')
    with pytest.raises(ValueError, match='outside its archive'):
        load_record(path, root=tmp_path / 'other')
    with pytest.raises(ValueError, match='receipt.json'):
        load_record(path.with_name('001.request.json'), root=tmp_path)


@pytest.mark.parametrize('target', ['receipt', 'request', 'response', 'directory'])
def test_loader_rejects_linked_archive_components_before_reading(tmp_path, monkeypatch, target):
    folder = tmp_path / 'calls'
    path, _, _, _ = record(folder)
    linked = {'receipt': path, 'request': path.with_name('001.request.json'),
              'response': path.with_name('001.response.txt'), 'directory': folder}[target]
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == linked or original(p))
    with pytest.raises(ValueError, match='symbolic links'):
        load_record(path, root=folder)
    with pytest.raises(ValueError, match='symbolic links'):
        list(iter_records(folder))
