"""Verify new native calls; keep historical and failed/rejected lineage distinct."""
from collections import Counter
from pathlib import Path
import hashlib
import json
from sdd.call_records import iter_records
from sdd.cli_provenance import verify_cli_receipt
from sdd.config import load

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT/'build/issue252/run'
CUTOFF = '2026-11-04T18:35:00'


def main():
    expected = load(RUN/'independent-review.yaml').agent
    rows, historical = [], 0
    imported=RUN/'historical-native-restoration-latest.json'
    preserved={row['receipt'] for row in json.loads(imported.read_bytes())['receipts']} if imported.exists() else set()
    newest=RUN/'historical-native-restoration-newest.json'
    if newest.exists():
        preserved.update(path.replace(chr(92),'/') for path in json.loads(newest.read_bytes())['receipt_paths'])
    for calls in sorted(RUN.rglob('calls')):
        if not calls.is_dir():
            continue
        for record in iter_records(calls):
            receipt = record.receipt
            if record.receipt_path.relative_to(RUN).as_posix() in preserved or receipt.get('completed_at','') < CUTOFF:
                historical += 1
                continue
            verified = verify_cli_receipt(record.request,record.raw,receipt,calls,expected)
            native = receipt['provider']
            rows.append(dict(receipt=record.receipt_path.relative_to(RUN).as_posix(),
                receipt_sha256=hashlib.sha256(record.receipt_path.read_bytes()).hexdigest(),
                request_sha256=receipt['request_sha256'],response_sha256=receipt['response_sha256'],
                stdout_sha256=verified['stdout_sha256'],tag=receipt['tag'],
                runner=expected.runner,model=expected.model,args=expected.args,
                arguments_verified=verified['arguments_verified'],cli_version=native['cli_version'],
                completed_at=receipt['completed_at'],human_review='pending'))
    result=dict(schema=1,status='verified',human_review='pending',historical_calls_excluded=historical,
        interpretation='Completed actual CLI calls include rejected drafts and retries, not successful manuscript count. Failed executions retain their original reports/logs.',
        counts=dict(Counter(row['tag'].split('_')[0] for row in rows)),calls=rows)
    (RUN/'native-call-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],new_completed_calls=len(rows),historical=historical,counts=result['counts'])),flush=True)


if __name__=='__main__':
    main()
