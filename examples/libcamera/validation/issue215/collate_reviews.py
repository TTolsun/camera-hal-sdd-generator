"""Attach native judgments only to the exact inventory inputs they reviewed."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from sdd.visual_audit import apply_reviews, digest
from sdd.call_records import iter_records
from sdd.cli_provenance import verify_cli_receipt
from sdd.config import load
from review_contract import SYSTEM, response_schema
from review_window_transport import prepare_review

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inventory', type=Path, required=True)
parser.add_argument('--review', type=Path, action='append', required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--reuse-unchanged', action='store_true', help='Keep original review identity only for exact current per-item fingerprints')
parser.add_argument('--ledger-only', action='store_true', help='Write the validated review ledger without duplicating the full item inventory')
args = parser.parse_args()
for output in (args.out, args.out.with_suffix('.report.json')):
    if output.exists() or output.is_symlink():
        raise ValueError('Preserve the existing output or input evidence: '+str(output))
report = json.loads(args.inventory.read_bytes())
current = {row['id']: row for row in report['items']}
ledger = dict(schema=1, items={}, human_review='pending', inventory_sha256=digest(report))
skipped = []
expected = load(Path(__file__).with_name('independent-review-profile.yaml')).agent
for path in args.review:
    review = json.loads(path.read_bytes())
    payload = json.loads(path.with_name('inputs.json').read_bytes())
    if (review['inventory_sha256'] != payload['inventory_sha256'] or review['input_sha256'] != digest(payload)
            or payload['source_commit'] != report['source_commit']
            or (not args.reuse_unchanged and review['inventory_sha256'] != digest(report))):
        raise ValueError('A review belongs to a different immutable inventory/input: '+str(path))
    if any(payload.get('visual_policy', {}).get(key) != report['policy'][key]
           for key in ('thresholds', 'signals', 'style_policy')):
        raise ValueError('The receipt-bound visual policy changed; review again: '+str(path))
    rules = payload.get('writing_rules', {})
    if (set(rules) != set(report['policy']['style_policy'])
            or any(hashlib.sha256(rules[name].encode()).hexdigest() != value
                   for name,value in report['policy']['style_policy'].items())):
        raise ValueError('Receipt-bound writing rules differ from the current policy: '+str(path))
    calls = path.parent/'prompts/calls'
    expected_schema = response_schema(payload['figures'].values())
    additional_manifest = {key:{k:v for k,v in value.items() if k != 'text'}
                           for key,value in payload['additional_source_windows'].items()}
    if review.get('additional_source_manifest') != additional_manifest:
        raise ValueError('Additional source manifest differs from the receipt-bound payload: '+str(path))
    native_user = None
    context_proof = path.with_name('native-context-proof.json')
    if context_proof.is_file():
        stored_proof = json.loads(context_proof.read_bytes())
        context_format = stored_proof.get('format')
        checked = context_format=='checked-presentation-source-windows-v1'
        native_user, package, proof = prepare_review(payload,
            structured=checked or context_format in {'structured-source-windows-v1','structured-source-windows-compact-json-v1'},
            compact_json=checked or context_format=='structured-source-windows-compact-json-v1',
            checked_presentation=checked)
        if (stored_proof != proof
                or (package is not None and json.loads(path.with_name('native-context.json').read_bytes()) != package)):
            raise ValueError('Archived shared review context differs from the complete input: '+str(path))
    matches = []
    for native in iter_records(calls):
        if (native.receipt.get('tag') == 'item-visual-review'
                and native.request['system'] == SYSTEM
                and native.request['response_schema'] == expected_schema
                and (native.request['user'] == native_user if native_user is not None
                     else json.loads(native.request['user']) == payload)
                and json.loads(native.raw).get('items') == review['items']):
            proof = verify_cli_receipt(native.request, native.raw, native.receipt, calls, expected)
            matches.append(dict(proof, receipt=str(native.receipt_path),
                receipt_sha256=hashlib.sha256(native.receipt_path.read_bytes()).hexdigest()))
    if len(matches) != 1:
        raise ValueError('Review must match one completed native Terra High receipt with the current independent-review contract: '+str(path))
    inputs = {row['id']: row for row in payload['items']}
    for row in review['items']:
        ident = row['id']
        if ident not in current or inputs[ident]['fingerprint'] != current[ident]['fingerprint']:
            if args.reuse_unchanged:
                skipped.append(dict(id=ident, review_record=str(path), reason='Changed/deleted item; original fingerprint not repinned'))
                continue
            raise ValueError('Review input fingerprint differs; do not repin: '+ident)
        ledger['items'][ident] = dict(row, fingerprint=inputs[ident]['fingerprint'],
            review_method='independent-native-codex-terra-high',
            review_record=str(path), review_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            reviewed_inventory_sha256=review['inventory_sha256'], reviewed_input_sha256=review['input_sha256'],
            native_provenance=matches[0],
            additional_source_manifest=additional_manifest)
ledger['skipped_stale_records'] = skipped
result = apply_reviews(copy.deepcopy(report), ledger)
for row in result['items']:
    record = ledger['items'].get(row['id'], {})
    for key in ['proposed_question', 'additional_source_windows', 'additional_source_manifest', 'review_record', 'review_sha256']:
        if key in record:
            row[key] = record[key]
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
if not args.ledger_only:
    args.out.with_suffix('.report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(items=len(result['items']), counts=result['counts'], unresolved=result['unresolved'], errors=result['errors']), ensure_ascii=False))
