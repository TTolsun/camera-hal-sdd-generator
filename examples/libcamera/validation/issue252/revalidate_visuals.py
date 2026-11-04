"""Revalidate historical graph metadata without changing prose or making inference."""
import hashlib
import json
from pathlib import Path
import re
from sdd.config import load, section_output
from sdd.document_metadata import split_frontmatter
from sdd.facts.model import KnowledgeModel
from sdd import generated_visuals
from sdd.render_profiles import for_page

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT/'build/issue252/run'


class NoInference:
    def chat(self, *args, **kwargs):
        raise ValueError('Historical graph failed current checks; select its CLI and regenerate explicitly.')


def main():
    cfg = load(RUN/'publication.yaml')
    model = KnowledgeModel.load(cfg.facts_path)
    rows = []
    for section in cfg.sections():
        rel = section_output(section)
        path = cfg.sdd_dir/rel
        if not path.is_file() or not generated_visuals.plans(cfg,section):
            continue
        selected = for_page(cfg,rel)
        original = path.read_text(encoding='utf-8')
        meta, body = split_frontmatter(original)
        try:
            generated_visuals.resolve(selected,model,section,meta.get('generated_visuals'))
            if rel!='request-lifecycle.md' and any('citation_binding_revalidation' in r for r in meta['generated_visuals']['records'].values()):
                baseline=(RUN/'published-base-manuscripts'/rel) if (RUN/'published-base-manuscripts'/rel).exists() else RUN.parent/'public/publication/issue214/manuscripts'/rel
                before=baseline.read_text(encoding='utf-8')
                assert split_frontmatter(before)[1]==body
                rows.append(dict(page=rel,original_sha256=hashlib.sha256(before.encode()).hexdigest(),updated_sha256=hashlib.sha256(original.encode()).hexdigest(),body_unchanged=True,new_inference=False,policy=generated_visuals.CITATION_BINDING_POLICY))
            continue
        except ValueError:
            pass
        artifact = generated_visuals.generate(selected,model,section,NoInference(),original)
        assert all(record['reused'] for record in artifact['records'].values())
        artifact['body_sha256'] = hashlib.sha256(body.strip().encode()).hexdigest()
        generated_visuals.resolve(selected,model,section,artifact)
        updated, count = re.subn(r'^generated_visuals: .+$',
            lambda _: 'generated_visuals: '+json.dumps(artifact,ensure_ascii=False),original,count=1,flags=re.M)
        assert count==1 and split_frontmatter(updated)[1]==body
        path.write_text(updated,encoding='utf-8',newline='\n')
        rows.append(dict(page=rel,original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                         updated_sha256=hashlib.sha256(updated.encode()).hexdigest(),
                         body_unchanged=True,new_inference=False,
                         policy=generated_visuals.CITATION_BINDING_POLICY))
    (RUN/'visual-revalidation.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':
    main()
