import hashlib, json, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import yaml

root=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
work=root/'build/issue253'
out=root/'docs/libcamera/records/issue253'
cost=work/'cost'
cost.mkdir(exist_ok=True)
original=root/'examples/libcamera/sdd.yaml'
cfg=yaml.safe_load(original.read_text(encoding='utf-8'))
cfg['source']['root']=str(work/'source')
cfg['source']['compile_commands']=str(cost/'missing-compile-commands.json')
cfg['output']={'facts_dir':str(cost/'facts'),'sdd_dir':str(work/'public/docs'),'diagrams_dir':str(cost/'diagrams')}
for k,v in cfg['paths'].items(): cfg['paths'][k]=str((original.parent/v).resolve())
cfg['paths']['products_file']=str((original.parent/cfg['products']['file']).resolve())
cfg['review']['coverage_triage']={'enabled':False}
(cost/'sdd.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
(cost/'facts').mkdir(exist_ok=True)
facts=root/'examples/libcamera/validation/issue211/runs/20261031-first-document-inputs/facts.json'
shutil.copyfile(facts,cost/'facts/facts.json')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
previous=json.loads((out/'cost.json').read_text(encoding='utf-8')) if (out/'cost.json').exists() else None
rows=previous['stages'] if previous else []
def run(name,args):
    start=datetime.now(timezone.utc).isoformat(); t=time.perf_counter()
    p=subprocess.run(args,cwd=root,capture_output=True,encoding='utf-8',errors='replace',timeout=600)
    elapsed=time.perf_counter()-t
    suffix=sum(r['stage']==name for r in rows)+1
    (out/f'{name}-{suffix}.stdout.txt').write_text(p.stdout,encoding='utf-8')
    (out/f'{name}-{suffix}.stderr.txt').write_text(p.stderr,encoding='utf-8')
    rows.append({'stage':name,'command':args,'started_at':start,'ended_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':elapsed,'returncode':p.returncode,'human_active_review_seconds':None,'wait_seconds':None})
    return p
run('source-diff',['git','-C',str(work/'source'),'diff','--stat','be909e49b7cfcbf8e888b6a17928ae06fd7f9a96','293d751a814e0d4c34e85ad457ccd9d5eefd1a61'])
run('impact',[sys.executable,'tools/run_sdd.py','--config',str(cost/'sdd.yaml'),'impact','--base','be909e49b7cfcbf8e888b6a17928ae06fd7f9a96','--head','293d751a814e0d4c34e85ad457ccd9d5eefd1a61','--fail-on-coverage-gap'])
impact=cost/'build/impact.json'
if impact.exists(): shutil.copyfile(impact,out/'impact.json')
ledger={'schema':1,'kind':'partial-historical-change-baseline','source_change':{'base':'be909e49b7cfcbf8e888b6a17928ae06fd7f9a96','head':'293d751a814e0d4c34e85ad457ccd9d5eefd1a61'},'facts':{'path':str(facts.relative_to(root)),'sha256':sha(facts),'reused':True,'new_extraction':False,'previous_facts_available':False},'stages':rows,'human_active_review_seconds':None,'savings_percent':None,'generation_calls':0,'translation_calls':0,'new_review_calls':0,'unfinished':['full-build-and-extraction','base-facts-comparison','generation-and-translation-if-affected','independent-review','human-active-review'],'limitations':['Only existing source293 facts are reused. qcam is absent from parsed_files.','Stage elapsed includes process startup and tool waiting. CPU time and environment delay are not separately measured.','No comparable earlier human review observation exists. Missing stages are not zero-cost success.']}
(out/'cost.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'stages':rows,'impact_exists':impact.exists()},ensure_ascii=False))
