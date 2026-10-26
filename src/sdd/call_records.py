"""Load archived model calls and verify hashes without choosing transport policy."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from .trial_workspace import contained_path, reject_symlinks


def canonical_request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CallRecord:
    receipt_path: Path
    request_path: Path
    response_path: Path
    receipt: dict[str, Any]
    request: dict[str, Any]
    raw: str


def load_record(receipt_path: Path, *, root: Path | None = None) -> CallRecord:
    """Preserve response bytes, including CRLF; reject missing or altered records."""
    original = reject_symlinks(receipt_path).resolve()
    root = reject_symlinks(root if root is not None else original.parent).resolve()
    try:
        relative = original.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'Call receipt is outside its archive: {receipt_path}') from exc
    receipt_path = contained_path(root, relative)
    if not receipt_path.name.endswith('.receipt.json'):
        raise ValueError(f'Expected a .receipt.json file: {receipt_path}')
    prefix = receipt_path.name.removesuffix('.receipt.json')
    request_path = contained_path(root, relative.with_name(prefix + '.request.json'))
    response_path = contained_path(root, relative.with_name(prefix + '.response.txt'))
    receipt = json.loads(receipt_path.read_bytes().decode('utf-8'))
    request = json.loads(request_path.read_bytes().decode('utf-8'))
    raw_bytes = response_path.read_bytes()
    raw = raw_bytes.decode('utf-8')
    if not isinstance(receipt, dict) or not isinstance(request, dict):
        raise ValueError(f'Call receipt and request must be JSON objects: {receipt_path}')
    if (receipt.get('request_sha256') != canonical_request_hash(request)
            or receipt.get('response_sha256') != hashlib.sha256(raw_bytes).hexdigest()):
        raise ValueError(f'Call record checksum mismatch: {receipt_path}')
    return CallRecord(receipt_path, request_path, response_path, receipt, request, raw)


def iter_records(root: Path) -> Iterator[CallRecord]:
    """Yield verified records in path order; consumers decide which are eligible."""
    root = reject_symlinks(root, recursive=True).resolve()
    for receipt in sorted(root.rglob('*.receipt.json')):
        yield load_record(receipt, root=root)
