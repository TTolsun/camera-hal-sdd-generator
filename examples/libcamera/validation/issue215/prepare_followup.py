"""Prepare a separate source-bound visual draft without altering its prior run."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import yaml

from sdd.config import load
from sdd.facts.model import KnowledgeModel

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--plans', type=Path, required=True)
args = parser.parse_args()
base, work = args.base.resolve(), args.work.resolve()
work.mkdir(parents=True, exist_ok=False)
for name in ['config', 'templates', 'run/manuscripts', 'run/facts']:
    shutil.copytree(base/name, work/name)
data = yaml.safe_load((base/'generation.yaml').read_bytes())
data['agent'] = yaml.safe_load(Path(__file__).with_name('generation-profile.yaml').read_bytes())['agent']
data['publication']['operation_id'] = 'issue215-visual-followup'
visuals = yaml.safe_load((work/'config/visuals.yaml').read_bytes())
plans = yaml.safe_load(args.plans.read_bytes())
for section, additions in plans.items():
    existing = visuals['sections'].setdefault(section, [])
    if {v['id'] for v in existing} & {v['id'] for v in additions}:
        raise ValueError('Follow-up plans must not replace existing visual plans')
    existing.extend(additions)
(work/'config/visuals.yaml').write_text(yaml.safe_dump(visuals, allow_unicode=True, sort_keys=False), encoding='utf-8')
(work/'generation.yaml').write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
cfg = load(work/'generation.yaml')
model = KnowledgeModel.load(cfg.facts_path)
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cfg.source_root, text=True).strip() != model.meta['source_commit']:
    raise ValueError('Reused evidence requires its exact source checkout')
if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=cfg.source_root, text=True).strip():
    raise ValueError('Reused evidence requires an unchanged source checkout')
(work/'followup-provenance.json').write_text(json.dumps(dict(
    base=str(base), base_config_sha256=hashlib.sha256((base/'generation.yaml').read_bytes()).hexdigest(),
    plans_sha256=hashlib.sha256(args.plans.read_bytes()).hexdigest(), source_commit=model.meta['source_commit'],
    facts_reuse='Unchanged section source selectors, exact clean source checkout; no new structural/source extraction',
    facts_sha256=hashlib.sha256(cfg.facts_path.read_bytes()).hexdigest(),
    sections=list(plans), human_review='pending'), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(work/'generation.yaml')
