"""Translate one catalog partition with the current full-catalog instructions."""
from pathlib import Path
import argparse,copy,json
from sdd.config import load
from sdd.llm import Agent
from sdd.translation import translate_missing,_batch_system

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config',type=Path,required=True)
p.add_argument('--catalog',type=Path,required=True)
p.add_argument('--sources',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--prompts',type=Path,required=True)
p.add_argument('--review-findings',type=Path,help='JSON source-to-finding map for native repairs; changed values still require independent review')
a=p.parse_args();cfg=load(a.config)
if (cfg.agent.kind,cfg.agent.runner,cfg.agent.model,cfg.agent.args)!=('cli','claude','claude-haiku-5-5',['--effort','high','--setting-sources','project,local']):raise ValueError('The selected native writer profile changed')
full=json.loads(a.catalog.read_bytes());sources=json.loads(a.sources.read_bytes())
if len(sources)!=len(set(sources)) or not set(sources)<=set(full['strings']):raise ValueError('Unknown or repeated partition sources')
# Instruction flags depend on these actual source strings. Including them is
# allowed to cause redundant real calls; no placeholder translation is seeded.
anchors=[next((k for k in full['strings'] if term in k),None) for term in ['절 전체 근거','예약된 호출']]
keys=list(dict.fromkeys(sources+[k for k in anchors if k is not None]))
part=copy.deepcopy(full);part['strings']={k:full['strings'][k] for k in keys}
if _batch_system(part['strings'])!=_batch_system(full['strings']):raise ValueError('Partition changed translation instructions')
agent=Agent(cfg.agent,a.prompts)
if a.review_findings:
    from sdd.translation_repair import repair
    findings=json.loads(a.review_findings.read_bytes())
    if set(findings)!=set(sources):raise ValueError('Repair findings must match the selected partition sources')
    result=copy.deepcopy(part);result['strings'].update(repair(cfg,part,findings,agent))
else:
    result=translate_missing(cfg,part,agent)
if any(not result['strings'][k] for k in keys):raise ValueError('Partition is incomplete')
with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print('Completed selected sources:',len(sources))
