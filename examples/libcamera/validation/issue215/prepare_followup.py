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
from sdd.trial_workspace import is_link

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--plans', type=Path, required=True)
parser.add_argument('--source-additions', type=Path, help='Append precise example source selectors before collecting new windows')
args = parser.parse_args()
base, work = args.base.resolve(), args.work.resolve()
root = Path(__file__).resolve().parents[4]
if (not work.is_relative_to(root) or work.is_relative_to(base) or base.is_relative_to(work)):
    raise ValueError('Choose a separate workspace output outside the previous run: '+str(work))
base_cfg = load(base/'generation.yaml')
source = base_cfg.source_root.resolve()
if work.is_relative_to(source) or source.is_relative_to(work):
    raise ValueError('Follow-up work must not overlap the source checkout: '+str(work))
if (base_cfg.facts_path.resolve() != (base/'run/facts/facts.json').resolve()
        or base_cfg.sdd_dir.resolve() != (base/'run/manuscripts').resolve()
        or base_cfg.sections_file.resolve() != (base/'config/sections.yaml').resolve()):
    raise ValueError('This example expects the documented base/config and base/run layout')
work.mkdir(parents=True, exist_ok=False)
for name in ['config', 'templates', 'run/manuscripts', 'run/facts']:
    shutil.copytree(base/name, work/name)
data = yaml.safe_load((base/'generation.yaml').read_bytes())
data['source']['root'] = str(base_cfg.source_root)
# Copied absolute output paths must never point back into the previous run.
data.setdefault('output', {}).update(facts_dir='run/facts', sdd_dir='run/manuscripts',
                                     diagrams_dir='run/manuscripts/diagrams')
data.setdefault('paths', {}).update(config='config', sections_file='config/sections.yaml',
                                   scenarios_file='config/scenarios.yaml')
data.setdefault('visuals', {})['file'] = 'config/visuals.yaml'
data['agent'] = yaml.safe_load(Path(__file__).with_name('generation-profile.yaml').read_bytes())['agent']
data['publication']['operation_id'] = 'issue215-visual-followup'
if args.source_additions:
    sections = yaml.safe_load((work/'config/sections.yaml').read_bytes())
    for sid, topics in yaml.safe_load(args.source_additions.read_bytes()).items():
        section = next(s for s in sections['sections'] if s['id']==sid)
        for tid, patch in topics.items():
            additions = patch['sources'] if isinstance(patch, dict) else patch
            topic = next(t for t in section['design_topics'] if t['id']==tid)
            if {s['id'] for s in topic['sources']} & {s['id'] for s in additions}:
                raise ValueError('Source additions must not replace historical selectors')
            topic['sources'].extend(additions)
            if isinstance(patch, dict) and 'parts' in patch:
                if topic.get('parts'):
                    raise ValueError('New source parts must not silently replace existing parts')
                topic['parts'] = patch['parts']
            for pid, refs in (patch.get('part_sources', {}) if isinstance(patch, dict) else {}).items():
                part = next(p for p in topic['parts'] if p['id']==pid)
                if not set(refs) <= {s['id'] for s in topic['sources']}:
                    raise ValueError('Part source additions must name existing source selectors')
                part['sources'] = list(dict.fromkeys([*part['sources'], *refs]))
            if isinstance(patch, dict) and patch.get('part_questions'):
                raise ValueError('Use part_revisions with a distinct new_id; preserve historical question identity')
            reserved = {p['id'] for p in topic.get('parts', [])}
            original, revised = set(reserved), set()
            for revision in (patch.get('part_revisions', []) if isinstance(patch, dict) else []):
                pid, new_id, question = revision['old_id'], revision['new_id'], revision['question']
                if (not isinstance(new_id, str) or not new_id.strip()
                        or new_id in reserved or pid not in original or pid in revised
                        or not isinstance(question, str) or not question.strip()):
                    raise ValueError('A revised question requires a nonempty distinct part identity')
                part = next(p for p in topic['parts'] if p['id']==pid)
                part.update(id=new_id, question=question)
                reserved.add(new_id)
                revised.add(pid)
    (work/'config/sections.yaml').write_text(yaml.safe_dump(sections,allow_unicode=True,sort_keys=False),encoding='utf-8')
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
for writable in (cfg.facts_dir, cfg.sdd_dir, cfg.diagrams_dir, cfg.build_dir):
    target = writable.resolve()
    if not target.is_relative_to(work) or is_link(writable):
        raise ValueError('Follow-up output is outside its isolated work root: '+str(writable))
    if (target.is_relative_to(base) or base.is_relative_to(target)
            or target.is_relative_to(cfg.source_root) or cfg.source_root.is_relative_to(target)):
        raise ValueError('Follow-up output overlaps immutable inputs: '+str(writable))
model = KnowledgeModel.load(cfg.facts_path)
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cfg.source_root, text=True).strip() != model.meta['source_commit']:
    raise ValueError('Reused evidence requires its exact source checkout')
if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=cfg.source_root, text=True).strip():
    raise ValueError('Reused evidence requires an unchanged source checkout')
if args.source_additions:
    from sdd.evidence import collect
    # collect reads ordinary code windows using git show at this exact commit;
    # product materials have their separate source-kind/provenance contract.
    collect(cfg, model)
    model.save(cfg.facts_path)
(work/'followup-provenance.json').write_text(json.dumps(dict(
    base=str(base), base_config_sha256=hashlib.sha256((base/'generation.yaml').read_bytes()).hexdigest(),
    plans_sha256=hashlib.sha256(args.plans.read_bytes()).hexdigest(), source_commit=model.meta['source_commit'],
    facts_reuse=('Original structural extraction retained; configured source windows collected again for explicit source/part changes'
                 if args.source_additions else 'Unchanged section source selectors, exact clean source checkout; no new structural/source extraction'),
    source_additions_sha256=hashlib.sha256(args.source_additions.read_bytes()).hexdigest() if args.source_additions else None,
    facts_sha256=hashlib.sha256(cfg.facts_path.read_bytes()).hexdigest(),
    sections=list(plans), human_review='pending'), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(work/'generation.yaml')
