"""Verify fresh native receipts; retain the earlier run's provenance unchanged."""
import argparse
import json
from pathlib import Path
from sdd.call_records import load_record
from sdd.cli_provenance import verify_cli_receipt
from sdd.config import load
from sdd.runtime_evidence import sha256

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
work = args.work.resolve()
retained = set(json.loads((work/'retained-receipts.json').read_text(encoding='utf-8')))
profiles = dict(claude=load(work/'generation.yaml').agent,
                codex=load(work/'new-document-review.yaml').agent)
for runner, model, arguments in [('claude','claude-haiku-5-5',['--effort','high','--setting-sources','project,local']),
                                  ('codex','gpt-6.1-terra',['-c','model_reasoning_effort="high"'])]:
    cfg = profiles[runner]
    if (cfg.kind,cfg.runner,cfg.model,cfg.args) != ('cli',runner,model,arguments):
        raise ValueError('Fresh execution profile differs from the selected CLI')
fresh, historical = [], []
for path in sorted(work.rglob('*.receipt.json')):
    if any(part.startswith('call-') for part in path.parts[:-1]):
        continue
    if sha256(path) in retained:
        historical.append(path.relative_to(work).as_posix())
        continue
    rec = load_record(path)
    if rec.receipt.get('transport') != 'cli':
        raise ValueError('A fresh call did not use the selected native CLI')
    runner = rec.receipt['provider']['runner']
    result = verify_cli_receipt(rec.request, rec.raw, rec.receipt, path.parent.parent, profiles[runner])
    fresh.append(dict(receipt=path.relative_to(work).as_posix(),sha256=sha256(path),
                      model=rec.receipt['model'],runner=runner,tag=rec.receipt['tag'],verified=result))
if {row['runner'] for row in fresh} != {'claude','codex'}:
    raise ValueError('Both selected independent native CLIs must have completed')
result = dict(schema=1,new_completed_calls=fresh,retained_historical_receipts=historical,
              scope='Exact CLI/receipt integrity only; semantic verdicts are separate and failed drafts remain failed.',
              historical_publication='https://github.com/TTolsun/libcamera-sdd/tree/5185973fcb98d2a7aa144f4ba5f4707c6a182ef4/publication/issue211-reader',
              http_calls=0,human_review='pending')
(work/'native-call-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(dict(fresh=len(fresh),retained=len(historical)))
