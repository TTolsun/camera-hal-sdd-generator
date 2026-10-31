"""Prepare an isolated, source-pinned addition without changing earlier runs."""
from pathlib import Path
import argparse
import json
import shutil
import yaml

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--previous', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
previous, work = args.previous.resolve(), args.work.resolve()
baseline = json.loads((previous/'run/facts/facts.json').read_text(encoding='utf-8'))['meta']['source_commit']
if baseline != '293d751a814e0d4c34e85ad457ccd9d5eefd1a61':
    raise ValueError('The virtual-principle addition requires the recorded issue211 baseline; commits must not be mixed')
work.mkdir(parents=True, exist_ok=False)
for name in ['config', 'run', 'build', 'historical-style']:
    shutil.copytree(previous/name, work/name)
for name in ['generation.yaml', 'publication.yaml', 'reader-verification.yaml',
             'historical-contract-review.yaml', 'new-document-review.yaml', 'site-intro.md']:
    text = (previous/name).read_text(encoding='utf-8')
    if name.endswith('.yaml'):
        text = text.replace(str(previous).replace('\\', '\\\\'), str(work).replace('\\', '\\\\'))
        text = text.replace(str(previous), str(work))
    (work/name).write_text(text, encoding='utf-8')
# Full source windows, diagram schema and the prior draft exceed the earlier
# reader run's character boundary. This is execution-local; no model arguments
# or public/global defaults change, and evidence is never truncated.
for name in ['generation.yaml', 'reader-verification.yaml', 'new-document-review.yaml']:
    path = work/name
    profile = yaml.safe_load(path.read_text(encoding='utf-8'))
    profile['agent']['max_input_chars'] = 128000
    path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding='utf-8')
# Exact copies are historical provenance, never fresh model calls.
from sdd.runtime_evidence import sha256
receipts = {sha256(p) for p in work.rglob('*.receipt.json')}
(work/'retained-receipts.json').write_text(json.dumps(sorted(receipts), indent=2)+'\n', encoding='utf-8')

base = Path(__file__).resolve().parent
topic = yaml.safe_load((base/'topic.yaml').read_text(encoding='utf-8'))
section = yaml.safe_load((root/'examples/libcamera/validation/issue211-reader/section.yaml').read_text(encoding='utf-8'))
section['design_requirements'].insert(1, dict(id=topic['id'], question=topic['question']))
section['design_topics'].insert(1, topic)
p = work/'config/sections.yaml'; data = yaml.safe_load(p.read_text(encoding='utf-8'))
data['sections'] = [section if s['id']==section['id'] else s for s in data['sections']]
p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8')
visual = yaml.safe_load((base/'visual.yaml').read_text(encoding='utf-8'))
p=work/'config/visuals.yaml'; data=yaml.safe_load(p.read_text(encoding='utf-8'))
overrides = {v['id']: v for v in yaml.safe_load((base/'retained-visual-overrides.yaml').read_text(encoding='utf-8'))}
data['sections'][section['id']] = [visual] + [overrides.get(v['id'], v) for v in data['sections'][section['id']]]
p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8')
print(json.dumps(dict(work=str(work), topics=[t['id'] for t in section['design_topics']], retained_receipts=len(receipts))))
