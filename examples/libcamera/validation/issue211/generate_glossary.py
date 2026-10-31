"""Draft missing reader definitions using the selected native writer."""
import argparse
import json
from pathlib import Path
import yaml
from sdd.config import load
from sdd.llm import Agent

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
sources = json.loads(Path(__file__).with_name('glossary-sources.json').read_text(encoding='utf-8'))
schema = {'type':'object','additionalProperties':False,'required':['terms'],
          'properties':{'terms':{'type':'array','minItems':len(sources),'maxItems':len(sources),'items':{'type':'object','additionalProperties':False,
             'required':['term','full','definition'],'properties':{'term':{'enum':list(sources)},'full':{'type':'string'},
               'definition':{'type':'string','maxLength':180}}}}}}
agent = Agent(load(Path(__file__).with_name('generation-profile.yaml')).agent, args.out/'prompts')
data = json.loads(agent.chat('Write short, clear Korean glossary definitions using only the supplied primary evidence. No tools. '
                             +(root/'style/README.md').read_text(encoding='utf-8'),
                             'Define every supplied term exactly once. One sentence per definition, ending 합니다/입니다. '
                             'No product support/performance or isolation guarantees. Full is the expansion; NV12 is a format identifier '
                             'and need not have an invented acronym expansion. UDMABUF is a Linux driver name, not a physical DMA validation claim. '
                             'NV12 has 8 bits PER COMPONENT, not 8 bits per pixel; state 성분당 8비트 explicitly. '
                             'VM is a general virtual-machine definition, not a claim that WSL distributions have separate kernels. '
                             'WSL covers the Windows Linux environment; WSL2 has its existing separate entry.\n'+json.dumps(sources),
                             tag='reader-glossary', response_schema=schema))
if {x['term'] for x in data['terms']} != set(sources):
    raise ValueError('Glossary terms differ from the requested reader vocabulary')
(args.out/'terms.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(agent.last_receipt)
