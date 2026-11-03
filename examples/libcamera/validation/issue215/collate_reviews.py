"""Attach native judgments only to the exact inventory inputs they reviewed."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from sdd.visual_audit import apply_reviews, digest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inventory', type=Path, required=True)
parser.add_argument('--review', type=Path, action='append', required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
report = json.loads(args.inventory.read_bytes())
current = {row['id']: row for row in report['items']}
ledger = dict(schema=1, items={}, human_review='pending', inventory_sha256=digest(report))
for path in args.review:
    review = json.loads(path.read_bytes())
    payload = json.loads(path.with_name('inputs.json').read_bytes())
    if (review['inventory_sha256'] != digest(report) or payload['inventory_sha256'] != digest(report)
            or review['input_sha256'] != digest(payload)):
        raise ValueError('A review belongs to a different immutable inventory/input: '+str(path))
    inputs = {row['id']: row for row in payload['items']}
    for row in review['items']:
        ident = row['id']
        if ident not in current or inputs[ident]['fingerprint'] != current[ident]['fingerprint']:
            raise ValueError('Review input fingerprint differs; do not repin: '+ident)
        ledger['items'][ident] = dict(row, fingerprint=inputs[ident]['fingerprint'],
            review_method='independent-native-codex-terra-high',
            review_record=str(path), review_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            additional_source_manifest=review.get('additional_source_manifest', {}))
result = apply_reviews(copy.deepcopy(report), ledger)
for row in result['items']:
    record = ledger['items'].get(row['id'], {})
    for key in ['proposed_question', 'additional_source_windows', 'additional_source_manifest', 'review_record', 'review_sha256']:
        if key in record:
            row[key] = record[key]
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
args.out.with_suffix('.report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(items=len(result['items']), counts=result['counts'], unresolved=result['unresolved'], errors=result['errors']), ensure_ascii=False))
