import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sdd.export_html import _split
project=ROOT/'build/issue251-extra/failure-project'
def snapshot():
    return {p.relative_to(project).as_posix():p.read_bytes() for d in [project/'sdd',project/'build/site'] for p in d.rglob('*') if p.is_file()}
before=snapshot()
results=[]
for command in ['generate','export-site','verify-site']:
    p=subprocess.run([sys.executable,str(ROOT/'tools/run_sdd.py'),'--config',str(project/'sdd.yaml'),command],capture_output=True,encoding='utf-8',errors='replace')
    results.append(dict(command=command,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
after=snapshot()
changes={k:dict(before=hashlib.sha256(before[k]).hexdigest(),after=hashlib.sha256(v).hexdigest()) for k,v in after.items() if before.get(k)!=v}
a,b=_split(before['sdd/completion.md'].decode('utf-8'))
c,d=_split(after['sdd/completion.md'].decode('utf-8'))
report=dict(stages=results,changes=changes,body_identical=b==d,metadata_changes={k:[a.get(k),c.get(k)] for k in a.keys()|c.keys() if a.get(k)!=c.get(k)})
(ROOT/'build/issue251-extra/repeat-diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(dict(changed=list(changes),body_identical=b==d,metadata_changes=list(report['metadata_changes'])),ensure_ascii=False))
