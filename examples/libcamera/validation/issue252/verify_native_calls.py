"""Verify new native calls; keep historical and failed/rejected lineage distinct."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re
import base64
from sdd.call_records import iter_records
from sdd.cli_provenance import verify_cli_receipt
from sdd.config import load
from sdd.state_io import save
from sdd.locking import locked

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT/'build/issue252/run'
CUTOFF = '2026-11-04T18:35:00'

# Frozen public input bindings, reviewed with this verifier's source revision.
# Derived from published original indexes and the prior digest-bound import.
# A new public baseline needs a recorded provenance update and source review.
HISTORICAL_IMPORT_MAP_SHA256 = {
    'historical-native-restoration-clarity.json': 'd8a8d63554ff65c6dec8e2c6aa4970f1815a9752783803c58bfc24342f8a2a9f',
    'historical-native-restoration-current.json': '208e85cc3ec76c703a01e846f2631b4af33c313e1cd22805c0dfac88ae00162d',
    'historical-native-restoration-initial.json': '8ac14528600e18d75de112a6570fbc0df670532e98964a0cfd535dd1495175e2',
    'historical-native-restoration-latest.json': '15cf529ec94750edb5de4357b1643e2f945e1ffe39a0064ff26293a8e6b321d2',
    'historical-native-restoration-navigation.json': '5d31a56cffd1bcdacbf20424e32e5208a730343d7218d3c327faebbce6fcbedf',
    'historical-native-restoration-newest.json': 'f5512a4e03a8d8a94d6ef7906fcce15c906cd6e26bf3c289454185a65a6fbc0a',
}


def historical_receipts(run, trusted_maps=None):
    """Verify every imported receipt before excluding it from new-call counts."""
    trusted_maps = HISTORICAL_IMPORT_MAP_SHA256 if trusted_maps is None else trusted_maps
    actual_maps = {p.name for p in run.glob('historical-native-restoration-*.json')}
    if actual_maps != set(trusted_maps):
        raise ValueError('Historical import map set changed')
    expected, maps = {}, []
    for name, trusted_digest in sorted(trusted_maps.items()):
        path = run/name
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != trusted_digest:
            raise ValueError('Historical import map changed: '+name)
        data = json.loads(raw)
        rows = data.get('receipts')
        if not isinstance(rows, list) or (data.get('receipt_paths') and not rows):
            raise ValueError('Historical import map needs receipt digests: '+path.name)
        for row in rows:
            rel, digest = row.get('receipt'), row.get('sha256')
            if (not isinstance(rel, str) or not rel
                    or '\\' in rel or ':' in rel or rel.startswith('/')
                    or '..' in rel.split('/')
                    or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise ValueError('Invalid historical receipt binding: '+path.name)
            target = run/rel
            if not target.resolve().is_relative_to(run.resolve()):
                raise ValueError('Historical receipt escapes run directory: '+rel)
            if rel in expected and expected[rel] != digest:
                raise ValueError('Conflicting historical receipt digests: '+rel)
            expected[rel] = digest
        maps.append(dict(path=path.name, sha256=hashlib.sha256(raw).hexdigest()))
    for rel, digest in expected.items():
        target = run/rel
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Historical receipt missing or changed: '+rel)
    return set(expected), maps


def _verify():
    expected = load(RUN/'independent-review.yaml').agent
    rows, historical = [], 0
    preserved, import_maps = historical_receipts(RUN)
    for calls in sorted(RUN.rglob('calls')):
        if not calls.is_dir():
            continue
        for record in iter_records(calls):
            receipt = record.receipt
            if record.receipt_path.relative_to(RUN).as_posix() in preserved:
                historical += 1
                continue
            if receipt.get('completed_at','') < CUTOFF:
                raise ValueError('Historical receipt has no digest binding: '+str(record.receipt_path))
            verified = verify_cli_receipt(record.request,record.raw,receipt,calls,expected)
            native = receipt['provider']
            rows.append(dict(receipt=record.receipt_path.relative_to(RUN).as_posix(),
                receipt_sha256=hashlib.sha256(record.receipt_path.read_bytes()).hexdigest(),
                request_sha256=receipt['request_sha256'],response_sha256=receipt['response_sha256'],
                stdout_sha256=verified['stdout_sha256'],tag=receipt['tag'],
                runner=expected.runner,model=expected.model,args=expected.args,
                arguments_verified=verified['arguments_verified'],cli_version=native['cli_version'],
                completed_at=receipt['completed_at'],human_review='pending'))
    final_preserved, final_maps = historical_receipts(RUN)
    if final_preserved != preserved or final_maps != import_maps:
        raise ValueError('Historical import bindings changed during verification')
    result=dict(schema=1,status='verified',human_review='pending',historical_calls_excluded=historical,
        historical_import_maps=import_maps, historical_import_receipts_verified=len(preserved),
        interpretation='Completed actual CLI calls include rejected drafts and retries, not successful manuscript count. Failed executions retain their original reports/logs.',
        counts=dict(Counter(row['tag'].split('_')[0] for row in rows)),calls=rows)
    return result


def main():
    with locked(RUN/'native-call-verification.lock','Native call verification'):
        return _attempt()


def _attempt():
    report = RUN/'native-call-verification.json'
    previous = None
    snapshot = None
    raw = None
    if report.exists():
        raw = report.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = dict(sha256=digest,bytes_base64=base64.b64encode(raw).decode('ascii'))
    # Invalidate success before archiving. The exact prior bytes survive even
    # when its archive cannot be written or a conflicting archive already exists.
    save(report,dict(schema=1,status='in-progress',human_review='pending',previous_snapshot=snapshot))
    try:
        if raw is not None:
            archive = RUN/'native-call-verification-history'/(snapshot['sha256']+'.json')
            archive.parent.mkdir(parents=True,exist_ok=True)
            if archive.exists():
                if archive.read_bytes() != raw:
                    raise ValueError('Prior native verification archive changed')
            else:
                archive.write_bytes(raw)
            previous = dict(path=archive.relative_to(RUN).as_posix(),sha256=snapshot['sha256'])
        result = _verify()
    except Exception as exc:
        save(report,dict(schema=1,status='failed',human_review='pending',
                         previous_report=previous,previous_snapshot=snapshot if previous is None else None,
                         error=str(exc)))
        raise
    result['previous_report'] = previous
    save(report,result)
    print(json.dumps(dict(status=result['status'],new_completed_calls=len(result['calls']),
                         historical=result['historical_calls_excluded'],counts=result['counts'])),flush=True)


if __name__=='__main__':
    main()
