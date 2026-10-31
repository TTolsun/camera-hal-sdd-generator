"""Separate native Terra review of reader definitions against primary excerpts."""
import argparse
import json
from pathlib import Path
from sdd.config import load
from sdd.llm import Agent
from sdd.runtime_evidence import sha256

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--definitions', type=Path)
parser.add_argument('--english', type=Path)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
base = Path(__file__).resolve().parent
sources = base/'glossary-sources.json'
terms = args.definitions or base/'runs/20261031-glossary-generation/terms.json'
schema = {'type':'object','additionalProperties':False,'required':['verdict','findings','scope'],
          'properties':{'verdict':{'enum':['pass','needs-revision']},'findings':{'type':'array','items':{'type':'string'}},'scope':{'type':'string'}}}
agent = Agent(load(base/'independent-review-profile.yaml').agent, args.out/'prompts')
english = ('\nACTUAL ENGLISH CATALOGUE PAIRS (also check translation equivalence)\n'+args.english.read_text(encoding='utf-8')) if args.english else ''
result = json.loads(agent.chat('Review glossary definitions for entailment, precision and reader comprehension. No tools. Return JSON.',
                               'Compare these actual selected-Claude Korean definitions with the primary-source excerpts/URLs. '
                               'NV12 is a format identifier, not an invented expansion; UDMABUF is a driver, not physical DMA proof; '
                               'generic VM definition must not imply independent kernels per WSL distribution. '
                               'Report unsupported claims or misleading definitions. Passing is not human approval.\nSOURCES\n'+sources.read_text(encoding='utf-8')+
                               '\nDEFINITIONS\n'+terms.read_text(encoding='utf-8')+english,tag='glossary-grounding',response_schema=schema))
(args.out/'review.json').write_text(json.dumps(dict(review=result,sources_sha256=sha256(sources),definitions_sha256=sha256(terms),english_sha256=sha256(args.english) if args.english else None,receipt=str(agent.last_receipt)),indent=2)+'\n',encoding='utf-8')
print(result['verdict'])
