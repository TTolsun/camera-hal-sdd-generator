"""Revalidate historical graph metadata without changing prose or making inference."""
import hashlib
import json
from pathlib import Path
import re
import yaml
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


def replace_visual_metadata(raw, artifact):
    """Reserialize valid YAML metadata and preserve the literal body bytes."""
    match=re.match(rb'^---\r?\n.*?\r?\n---\r?\n',raw,re.S)
    assert match, 'Historical manuscript must have complete frontmatter.'
    text=raw.decode('utf-8').replace('\r\n','\n')
    meta,_=split_frontmatter(text)
    other={key:value for key,value in meta.items() if key!='generated_visuals'}
    meta['generated_visuals']=artifact
    header='---\n'+yaml.safe_dump(meta,allow_unicode=True,sort_keys=False)+'---\n'
    if raw.startswith(b'---\r\n'):
        header=header.replace('\n','\r\n')
    updated=header.encode('utf-8')+raw[match.end():]
    parsed,_=split_frontmatter(updated.decode('utf-8').replace('\r\n','\n'))
    assert {key:value for key,value in parsed.items() if key!='generated_visuals'}==other
    return updated


def retain_revalidation_row(row, before, after):
    """A repeat check retains its first recorded raw-byte identities."""
    if (hashlib.sha256(before).hexdigest()!=row['original_sha256']
            or hashlib.sha256(after).hexdigest()!=row['updated_sha256']):
        raise ValueError('Historical revalidation byte identities changed.')
    def body(raw):
        match=re.match(rb'^---\r?\n.*?\r?\n---\r?\n',raw,re.S)
        if not match:
            raise ValueError('Missing original frontmatter boundary.')
        return raw[match.end():]
    if body(before)!=body(after):
        raise ValueError('Historical revalidation changed literal body bytes.')
    return dict(row)


def original_snapshot(rel, raw):
    path=RUN/'visual-revalidation-originals'/hashlib.sha256(raw).hexdigest()/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        assert path.read_bytes()==raw
    else:
        path.write_bytes(raw)
    return path


def main():
    cfg = load(RUN/'publication.yaml')
    model = KnowledgeModel.load(cfg.facts_path)
    report=RUN/'visual-revalidation.json'
    previous={}
    if report.exists():
        raw=report.read_bytes()
        previous={row['page']:row for row in json.loads(raw)}
        history=RUN/'visual-revalidation-history';history.mkdir(exist_ok=True)
        saved=history/(hashlib.sha256(raw).hexdigest()+'.json')
        if saved.exists():
            assert saved.read_bytes()==raw
        else:
            saved.write_bytes(raw)
    rows = []
    for section in cfg.sections():
        rel = section_output(section)
        path = cfg.sdd_dir/rel
        # The selected primary is owned by real generation and its independent
        # reviews; this helper only carries historical non-selected pages.
        if rel=='request-lifecycle.md':
            continue
        if not path.is_file() or not generated_visuals.plans(cfg,section):
            continue
        selected = for_page(cfg,rel)
        original_raw = path.read_bytes()
        original = original_raw.decode('utf-8').replace('\r\n','\n')
        meta, body = split_frontmatter(original)
        try:
            generated_visuals.resolve(selected,model,section,meta.get('generated_visuals'))
        except ValueError:
            resolved=False
        else:
            resolved=True
        if resolved:
            if rel!='request-lifecycle.md' and any('citation_binding_revalidation' in r for r in meta['generated_visuals']['records'].values()):
                baseline=(RUN/'published-base-manuscripts'/rel) if (RUN/'published-base-manuscripts'/rel).exists() else RUN.parent/'public/publication/issue214/manuscripts'/rel
                prior=previous.get(rel)
                if prior and prior['updated_sha256']==hashlib.sha256(original_raw).hexdigest():
                    snapshot=RUN/'visual-revalidation-originals'/rel
                    origin=RUN/prior['original_file'] if prior.get('original_file') else snapshot if snapshot.exists() else baseline
                    before=origin.read_bytes()
                    retained=retain_revalidation_row(prior,before,original_raw)
                    if not snapshot.exists():
                        snapshot.parent.mkdir(parents=True,exist_ok=True)
                        snapshot.write_bytes(before)
                    rows.append(retained)
                elif baseline.read_bytes()==original_raw:
                    snapshot=original_snapshot(rel,original_raw)
                    rows.append(dict(page=rel,original_sha256=hashlib.sha256(original_raw).hexdigest(),updated_sha256=hashlib.sha256(original_raw).hexdigest(),original_file=snapshot.relative_to(RUN).as_posix(),body_unchanged=True,new_inference=False,policy=generated_visuals.CITATION_BINDING_POLICY,scope='Checked inherited metadata; no new rewrite.'))
                else:
                    raise ValueError('Missing original byte proof for a prior revalidation: '+rel)
            continue
        artifact = generated_visuals.generate(selected,model,section,NoInference(),original)
        assert all(record['reused'] for record in artifact['records'].values())
        artifact['body_sha256'] = hashlib.sha256(body.strip().encode()).hexdigest()
        generated_visuals.resolve(selected,model,section,artifact)
        updated = replace_visual_metadata(original_raw,artifact)
        assert split_frontmatter(updated.decode('utf-8').replace('\r\n','\n'))[1]==body
        snapshot=original_snapshot(rel,original_raw)
        path.write_bytes(updated)
        rows.append(dict(page=rel,original_sha256=hashlib.sha256(original_raw).hexdigest(),
                         updated_sha256=hashlib.sha256(updated).hexdigest(),
                         original_file=snapshot.relative_to(RUN).as_posix(),
                         body_unchanged=True,new_inference=False,
                         policy=generated_visuals.CITATION_BINDING_POLICY))
    report.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':
    main()
