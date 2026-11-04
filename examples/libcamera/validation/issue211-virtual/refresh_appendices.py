"""Snapshot previous managed appendices, or apply a verified encoding-only refresh."""
from pathlib import Path
import argparse,json,shutil
from sdd.config import load
from sdd.facts.model import KnowledgeModel
from sdd.runtime_evidence import sha256
from sdd.scenario_sections import appendix

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config',type=Path,required=True)
p.add_argument('--snapshot',type=Path)
p.add_argument('--apply',type=Path)
p.add_argument('--backup',type=Path)
p.add_argument('--report',type=Path)
a=p.parse_args();cfg=load(a.config);model=KnowledgeModel.load(cfg.facts_path)
sections=[s for s in cfg.sections() if s.get('scenario')]
if bool(a.snapshot)==bool(a.apply):p.error('Choose exactly one of --snapshot or --apply')
if a.snapshot:
    rows={}
    for s in sections:
        doc,meta=appendix(cfg,model,s)
        rows[s['id']]=dict(source_commit=model.meta['source_commit'],metadata=meta,overview=doc.overview,details=doc.details)
    with a.snapshot.open('x',encoding='utf-8') as f:json.dump(rows,f,ensure_ascii=False,indent=2)
else:
    if not a.backup or not a.report:p.error('--apply requires --backup and --report')
    if a.backup.exists() or a.report.exists():raise ValueError('Preserve prior backup and report paths')
    from sdd.scenario_sections import refresh_encoded_appendix
    from sdd.render_profiles import for_page
    rows=json.loads(a.apply.read_bytes());assert set(rows)=={s['id'] for s in sections}
    prepared=[]
    for s in sections:
        rel=s.get('output',s['id']+'.md');path=cfg.sdd_dir/rel;old=path.read_text(encoding='utf-8')
        new=refresh_encoded_appendix(for_page(cfg,rel),model,s,old,rows[s['id']])
        prepared.append((rel,path,old,new))
    a.backup.mkdir(parents=True,exist_ok=False);report=[]
    for rel,path,old,new in prepared:
        target=a.backup/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    for rel,path,old,new in prepared:
        before=sha256(path)
        if new!=old:path.write_text(new,encoding='utf-8',newline='\n')
        report.append(dict(path=rel,previous_sha256=before,sha256=sha256(path),changed=new!=old,new_inference=False))
    with a.report.open('x',encoding='utf-8') as f:json.dump(dict(source_commit=model.meta['source_commit'],scope='Native prose retained; only source-identical managed Mermaid encoding refreshed',files=report),f,indent=2)
    print('Verified encoding-only appendices:',len(report))
