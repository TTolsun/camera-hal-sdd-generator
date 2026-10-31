"""Native revision of one rejected definition; keep other native definitions."""
import argparse
import json
from pathlib import Path
from sdd.config import load
from sdd.llm import Agent

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=False)
data=json.loads((base/'runs/20261031-glossary-generation-2/terms.json').read_text(encoding='utf-8'))
source=json.loads((base/'glossary-sources.json').read_text(encoding='utf-8'))['NV12']
schema={'type':'object','additionalProperties':False,'required':['term','full','definition'],
        'properties':{'term':{'const':'NV12'},'full':{'type':'string'},'definition':{'type':'string','maxLength':180}}}
agent=Agent(load(base/'generation-profile.yaml').agent,args.out/'prompts')
result=json.loads(agent.chat('Write one precise Korean glossary definition from the primary excerpt. No tools. Return JSON.',
                             'Revise NV12. State 성분당 8비트, 4:2:0, first plane Y luma and second plane Cb/Cr alternating interleaved chroma, '
                             'linear contiguous memory. Do not merely say Cb/Cr order; explain alternating storage. '
                             'One or two short complete Korean sentences, no hardware or performance claim. NV12 is an identifier, no invented expansion.\n'+json.dumps(source),
                             tag='nv12-definition-revision',response_schema=schema))
data['terms']=[result if term['term']=='NV12' else term for term in data['terms']]
(args.out/'terms.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(agent.last_receipt)
