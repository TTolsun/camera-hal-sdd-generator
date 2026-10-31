"""Native revision of one rejected definition; keep other native definitions."""
import argparse
import json
from pathlib import Path
from sdd.config import load
from sdd.llm import Agent

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--term',choices=('NV12','VM'),default='NV12')
parser.add_argument('--draft',type=Path)
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=False)
data=json.loads((args.draft or base/'runs/20261031-glossary-generation-2/terms.json').read_text(encoding='utf-8'))
source=json.loads((base/'glossary-sources.json').read_text(encoding='utf-8'))[args.term]
schema={'type':'object','additionalProperties':False,'required':['term','full','definition'],
        'properties':{'term':{'const':args.term},'full':{'type':'string'},'definition':{'type':'string','maxLength':180}}}
agent=Agent(load(base/'generation-profile.yaml').agent,args.out/'prompts')
instructions = ('Revise NV12. State 성분당 8비트, 4:2:0, first plane Y luma and second plane Cb/Cr alternating interleaved chroma, '
                             'linear contiguous memory. Do not merely say Cb/Cr order; explain alternating storage. '
                             'NV12 is an identifier, no invented expansion.') if args.term == 'NV12' else (
                             'Define a general Virtual Machine, not only a cloud VM. Use 물리 컴퓨터 rather than 물리 서버; '
                             'it is software-based and runs its own OS/apps using virtualized host resources. '
                             'Do not imply a separate kernel for each WSL distribution or physical isolation guarantees.')
result=json.loads(agent.chat('Write one precise Korean glossary definition from the primary source. No tools. Return JSON.',
                             instructions+' One or two short complete Korean sentences, no performance claim.\n'+json.dumps(source),
                             tag='definition-revision',response_schema=schema))
data['terms']=[result if term['term']==args.term else term for term in data['terms']]
(args.out/'terms.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(agent.last_receipt)
