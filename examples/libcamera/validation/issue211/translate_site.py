"""Model-free historical rendering; separate native Claude translation calls."""
import argparse
import json
from pathlib import Path
import shutil
from sdd.config import load
from sdd.localization_cli import prepare_catalog
from sdd.translation import translate_missing
from sdd.llm import Agent
from sdd.cli_agent import arguments

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
work = root/'build/issue211-publication'
render_cfg = load(work/'publication.yaml')
writer_cfg = load(work/'generation.yaml')
if (writer_cfg.agent.kind,writer_cfg.agent.runner,writer_cfg.agent.model,writer_cfg.agent.args) != (
        'cli','claude','claude-haiku-5-5',['--effort','high','--setting-sources','project,local']):
    raise ValueError('Translation writer differs from the selected issue profile')
(args.out/'profiles.json').write_text(json.dumps(dict(rendering=dict(model_calls=False,agent=render_cfg.agent.label,
                                                                  purpose='Authenticate retained historical visuals only'),
                                                     translation=dict(agent=writer_cfg.agent.label,arguments=arguments(writer_cfg.agent))),indent=2)+'\n',encoding='utf-8')
candidate = args.out/'english.prepared.json'
shutil.copyfile(work/'run/english.json',candidate)
prepared = prepare_catalog(render_cfg,candidate,translate=False)
catalog = json.loads(candidate.read_text(encoding='utf-8'))
agent = Agent(writer_cfg.agent,work/'build/translation-prompts')
translated = translate_missing(writer_cfg,catalog,agent)
if any(not value for value in translated['strings'].values()):
    raise ValueError('English catalog still has missing values')
complete = args.out/'english.complete.json'
complete.write_text(json.dumps(translated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(complete,work/'run/english.json')
(args.out/'translation.json').write_text(json.dumps(dict(schema=1,prepared=prepared,missing_after=0,
                                                       human_review='pending',writer=writer_cfg.agent.label),indent=2)+'\n',encoding='utf-8')
print(json.dumps(prepared),flush=True)
