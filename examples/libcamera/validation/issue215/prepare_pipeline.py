"""Prepare a standalone pipeline-handler draft from immutable public inputs.

Retains original structural facts at 293 and extracts configured source windows
again from the matching official checkout. Does not publish or alter another run.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import yaml

from sdd.config import load
from sdd.evidence import collect
from sdd.facts.model import KnowledgeModel

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--public', type=Path, required=True)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
public, source, work = args.public.resolve(), args.source.resolve(), args.work.resolve()
baseline = public/'publication/issue214'
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() != '293d751a814e0d4c34e85ad457ccd9d5eefd1a61':
    raise ValueError('The archived structural input requires its exact official 293 source checkout')
work.mkdir(parents=True, exist_ok=False)
for origin, target in [(baseline/'config', work/'config'), (ROOT/'templates', work/'templates')]:
    shutil.copytree(origin, target)
(work/'run/manuscripts').mkdir(parents=True)
for manuscript in (public/'docs').rglob('*.md'):
    rel = manuscript.relative_to(public/'docs')
    if rel.parts[0] == 'en':
        continue
    target = work/'run/manuscripts'/rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manuscript, target)
data = yaml.safe_load((baseline/'profiles/generation.yaml').read_bytes())
data['agent'] = yaml.safe_load((Path(__file__).with_name('generation-profile.yaml')).read_bytes())['agent']
data['source'] = dict(root=str(source), compile_commands=str(source/'build/compile_commands.json'),
                      exclude=['subprojects/**', 'test/**', 'build/**'], ndk_build=dict(enabled=False))
data['output'] = dict(facts_dir='run/facts', sdd_dir='run/manuscripts', diagrams_dir='run/manuscripts/diagrams')
data['paths'] = dict(sections_file='config/sections.yaml', scenarios_file='config/scenarios.yaml',
                     prompts=str(ROOT/'examples/libcamera/prompts'), templates='templates', style=str(ROOT/'style'),
                     products_file='config/products.yaml')
data['products'] = dict(file='config/products.yaml')
data['site'] = dict(enabled=False)
data['publication'] = dict(operation_id='issue215-pipeline-draft')
data['review'].update(design_grounding=True, cli_checkpoint=True)
sections = yaml.safe_load((work/'config/sections.yaml').read_bytes())
section = next(s for s in sections['sections'] if s['id'] == 'pipeline-handler')
# Add the exact dispatch implementation requested by the independent review.
shutdown = next(t for t in section['design_topics'] if t['id'] == 'shutdown')
shutdown['sources'].append(dict(id='cancelled-dispatch', file='src/libcamera/pipeline_handler.cpp',
    start='void PipelineHandler::doQueueRequest(Request *request)', end='\n}'))
next(part for part in shutdown['parts'] if part['id'] == 'pending')['sources'].append('cancelled-dispatch')
(work/'config/sections.yaml').write_text(yaml.safe_dump(sections, allow_unicode=True, sort_keys=False), encoding='utf-8')
visuals = yaml.safe_load((work/'config/visuals.yaml').read_bytes())
visuals['sections'].setdefault('pipeline-handler', []).extend(yaml.safe_load(Path(__file__).with_name('stop-visual.yaml').read_bytes()))
(work/'config/visuals.yaml').write_text(yaml.safe_dump(visuals, allow_unicode=True, sort_keys=False), encoding='utf-8')
data['visuals'] = dict(file='config/visuals.yaml', max_nodes=12, on_stale='error')
(work/'generation.yaml').write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
cfg = load(work/'generation.yaml')
raw = gzip.decompress((baseline/'facts293.json.gz').read_bytes())
model = KnowledgeModel.from_dict(json.loads(raw))
collect(cfg, model)
model.save(cfg.facts_path)
(work/'input-provenance.json').write_text(json.dumps(dict(
    public_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=public, text=True).strip(),
    source_commit=model.meta['source_commit'], structural_facts_sha256=hashlib.sha256(raw).hexdigest(),
    derived_facts_sha256=hashlib.sha256(cfg.facts_path.read_bytes()).hexdigest(),
    extraction='Configured source windows re-extracted from the exact commit; original structural extraction retained',
    source_findings=[key for key, value in model.evidence.items() if value.get('status') != 'available'],
    generation_profile=data['agent'], human_review='pending'), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(work/'generation.yaml')
