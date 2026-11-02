"""Compare all PR69 contract bytes outside the timed enforcement experiment."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sdd.config import load
from sdd.facts.model import KnowledgeModel
from sdd.validation_stage import stage
from sdd import consistency

WORK = ROOT/'build/issue214'
spec = importlib.util.spec_from_file_location('sdd._issue214_original', WORK/'baseline/src/sdd/consistency.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
cfg = load(WORK/'fixture/publication.yaml')
model = KnowledgeModel.load(cfg.facts_path)
rows = []
with stage() as inputs:
    inputs.pin(cfg, model)
    for group in consistency.groups(cfg):
        before = original.request(cfg, model, group)
        after = consistency.request(cfg, model, group)
        assert before == after, group['id']
        def wire(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        assert wire(before) == wire(after)
        rows.append(dict(contract=group['id'], sha256=hashlib.sha256(wire(after)).hexdigest(),
                         claims=len(after['claims']), sources=len(after['sources']), byte_identical=True))
report = dict(status='passed', model_calls=0, contracts=rows,
              original_policy=original.policy_hash(), current_policy=consistency.policy_hash(),
              current_policy_requires_independent_review=True)
(WORK/'payload-comparison.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report), flush=True)
