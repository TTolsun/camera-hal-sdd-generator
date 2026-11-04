import hashlib,json,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
from sdd.config import load
from sdd.llm import Agent
root=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
record=root/'docs/libcamera/records/issue253'
source=root/'build/issue253/source'
schema={'type':'object','additionalProperties':False,'properties':{'verdict':{'type':'string'},'findings':{'type':'array','items':{'type':'string'}},'scope_limitations':{'type':'array','items':{'type':'string'}}},'required':['verdict','findings','scope_limitations']}
diff=subprocess.run(['git','-C',str(source),'show','--format=fuller','293d751a814e0d4c34e85ad457ccd9d5eefd1a61'],capture_output=True,encoding='utf-8',check=True).stdout
user=json.dumps({'task':'Independently review this partial cost measurement against the actual upstream diff and coverage. Identify overclaims, mishandled omissions and required next steps. Do not waive findings or claim human approval. This is not a new document generation.', 'protocol':(record/'protocol.md').read_text(encoding='utf-8'), 'diff':diff,'impact':json.loads((record/'impact.json').read_text(encoding='utf-8')),'cost':json.loads((record/'cost.json').read_text(encoding='utf-8')),'existing_overview_body':(root/'build/issue253/public/docs/overview.md').read_text(encoding='utf-8').split('\n---\n',1)[-1]},ensure_ascii=False)
t=time.perf_counter(); start=datetime.now(timezone.utc).isoformat()
try:
    agent=Agent(load(record/'review.yaml').agent,dump_dir=root/'examples/libcamera/validation/issue253/runs/cost-review')
    raw=agent.chat('You are an independent source-grounding reviewer. Use only the supplied inputs and return the schema JSON. Review is automatic, never human approval.',user,tag='cost-source-review',response_schema=schema)
    (record/'cost-review.json').write_text(json.dumps(json.loads(raw),ensure_ascii=False,indent=2),encoding='utf-8')
    status='completed'
except Exception as exc:
    (record/'cost-review-error.txt').write_text(str(exc),encoding='utf-8');status='failed'
elapsed=time.perf_counter()-t
ledger=json.loads((record/'cost.json').read_text(encoding='utf-8'))
ledger['stages'].append({'stage':'independent-cli-source-review','started_at':start,'ended_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':elapsed,'status':status,'human_active_review_seconds':None,'wait_seconds':None})
ledger['new_review_calls']=sum(1 for p in (root/'examples/libcamera/validation/issue253/runs/cost-review').glob('calls/**/*.receipt.json'))
if status=='completed':ledger['unfinished'].remove('independent-review')
(record/'cost.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':status,'elapsed_seconds':elapsed}))
