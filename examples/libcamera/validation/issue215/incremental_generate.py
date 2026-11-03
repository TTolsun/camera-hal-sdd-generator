"""Generate one new visual per isolated stage, retaining successful prior work.

The existing receipt-bound #214 design checkpoints and manuscript visual reuse
are validated by the generator. Failed visual responses are never substituted
for new calls. A failed stage stops; prior stages remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, required=True)
parser.add_argument('--plans', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--checkpoint-source', type=Path)
args = parser.parse_args()
base, work = args.base.resolve(), args.work.resolve()
if not work.is_relative_to(ROOT) or work.exists():
    raise ValueError('Choose a new isolated workspace output')
work.mkdir(parents=True)
plans = yaml.safe_load(args.plans.read_bytes())
if len(plans) != 1:
    raise ValueError('Select exactly one section per incremental run')
section, values = next(iter(plans.items()))
progress = dict(section=section, status='running', stages=[], human_review='pending')
checkpoint_source = args.checkpoint_source.resolve() if args.checkpoint_source else None
for index, plan in enumerate(values, 1):
    stage = work/f'step-{index:02d}'
    selected = work/f'plan-{index:02d}.yaml'
    selected.write_text(yaml.safe_dump({section:[plan]},allow_unicode=True,sort_keys=False),encoding='utf-8')
    subprocess.run([sys.executable,str(Path(__file__).with_name('prepare_followup.py')),
                    '--base',str(base),'--work',str(stage),'--plans',str(selected)],check=True,cwd=ROOT)
    reused = {}
    if checkpoint_source:
        for relative in ['build/cli-checkpoints','build/prompts/calls','build/prompts/cli']:
            origin = checkpoint_source/relative
            if not origin.exists():
                continue
            shutil.copytree(origin,stage/relative)
            reused.update({(Path(relative)/p.relative_to(origin)).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in origin.rglob('*') if p.is_file()})
    (stage/'checkpoint-copy-provenance.json').write_text(json.dumps(dict(
        source=str(checkpoint_source) if checkpoint_source else None, files=reused,
        scope='Byte-identical completed design checkpoints and native receipts; generator revalidates identity and policy'),indent=2)+'\n',encoding='utf-8')
    with (work/f'generation-{index:02d}.log').open('w',encoding='utf-8') as log:
        result = subprocess.run([sys.executable,'-c','from sdd.cli import main; raise SystemExit(main())',
            '--config',str(stage/'generation.yaml'),'generate','--sections',section],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    progress['stages'].append(dict(stage=index,visual=plan['id'],exit_code=result.returncode,output=str(stage)))
    progress['status'] = 'failed' if result.returncode else ('completed-generation-only' if index==len(values) else 'running')
    (work/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(section,plan['id'],'exit='+str(result.returncode),flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    base = checkpoint_source = stage
