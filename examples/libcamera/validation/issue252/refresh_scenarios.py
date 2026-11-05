"""Apply the existing encoding-only refresh using original generator snapshots."""
import hashlib
import json
from pathlib import Path
from sdd.config import load, section_output
from sdd.facts.model import KnowledgeModel
from sdd.render_profiles import for_page
from sdd.scenario_sections import refresh_encoded_appendix

ROOT=Path(__file__).resolve().parents[4]
RUN=ROOT/'build/issue252/run'


def main():
    cfg=load(RUN/'publication.yaml')
    model=KnowledgeModel.load(cfg.facts_path)
    rows=[]
    for section in cfg.sections():
        if not section.get('scenario'):
            continue
        path=cfg.sdd_dir/section_output(section)
        original=path.read_text(encoding='utf-8')
        previous=json.loads((RUN/'historical-scenario-snapshots'/(section['scenario']+'.json')).read_bytes())
        updated=refresh_encoded_appendix(for_page(cfg,section_output(section)),model,section,original,previous)
        path.write_text(updated,encoding='utf-8',newline='\n')
        rows.append(dict(page=section_output(section),original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                         updated_sha256=hashlib.sha256(updated.encode()).hexdigest(),new_inference=False,
                         scope='Existing managed Mermaid literal encoding refresh; source/graph/prose unchanged.'))
    (RUN/'scenario-format-refresh.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':
    main()
