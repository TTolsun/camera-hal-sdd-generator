"""Preserve the concurrently published base, verified against its live manifest."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import yaml
from sdd.config import load
from sdd.document_metadata import split_frontmatter
from sdd import evidence
from sdd.facts.model import KnowledgeModel

ROOT=Path(__file__).resolve().parents[4]
RUN=ROOT/'build/issue252/run'
PUBLIC=RUN.parent/'public'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,data):
    path.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')


def main():
    if (RUN/'public-base-integration.json').exists():
        raise ValueError('Keep the frozen base; use an explicit new integration for a newer release.')
    profile=PUBLIC/'publication/issue248/publication.yaml'
    base=load(profile)
    manifest=json.loads((PUBLIC/'docs/site-manifest.json').read_bytes())
    # Referenced local public inputs must be exactly those already published.
    for key,path in [('facts',base.facts_path),('sections',base.sections_file),
                     ('visuals',base.root/base.visuals.file)]:
        assert sha(path)==manifest['inputs'][key],key
    for key,digest in manifest['inputs'].items():
        if key.startswith('markdown/'):
            assert sha(base.sdd_dir/key.removeprefix('markdown/'))==digest,key
    ours=json.loads((RUN/'facts/facts.json').read_bytes())
    theirs=json.loads(base.facts_path.read_bytes())
    assert all(ours[key]==theirs[key] for key in ours if key!='evidence')
    old=RUN/'before-public-base-integration'
    old.mkdir()
    for name in ['config','manuscripts']:
        shutil.copytree(RUN/name,old/name)
    shutil.copyfile(RUN/'english.json',old/'english.json')
    shutil.copyfile(RUN/'facts/facts.json',old/'facts.json')
    selected=next(s for s in yaml.safe_load((RUN/'config/sections.yaml').read_bytes())['sections'] if s['id']=='request-lifecycle')
    selected_visuals=yaml.safe_load((RUN/'config/visuals.yaml').read_bytes())['sections']['request-lifecycle']
    additions=[t for t in yaml.safe_load((RUN/'config/glossary.yaml').read_bytes())['terms'] if t['term'] in ['QBUF','STREAMOFF','DQBUF']]
    for file in base.config_dir.rglob('*'):
        if file.is_file():
            target=RUN/'config'/file.relative_to(base.config_dir)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,target)
    sections=yaml.safe_load((RUN/'config/sections.yaml').read_bytes())
    sections['sections']=[selected if s['id']=='request-lifecycle' else s for s in sections['sections']]
    write(RUN/'config/sections.yaml',sections)
    visuals=yaml.safe_load((RUN/'config/visuals.yaml').read_bytes())
    assert {v['id'] for v in visuals['sections']['request-lifecycle']} <= {v['id'] for v in selected_visuals}
    visuals['sections']['request-lifecycle']=selected_visuals
    write(RUN/'config/visuals.yaml',visuals)
    glossary=yaml.safe_load((RUN/'config/glossary.yaml').read_bytes())
    assert not {t['term'] for t in additions} & {t['term'] for t in glossary['terms']}
    glossary['terms']+=additions
    next(t for t in glossary['terms'] if t['term']=='errno')['aliases'].append('ENOENT')
    write(RUN/'config/glossary.yaml',glossary)
    copied=[]
    for source in base.sdd_dir.rglob('*'):
        if not source.is_file():continue
        rel=source.relative_to(base.sdd_dir)
        frozen=RUN/'published-base-manuscripts'/rel
        frozen.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,frozen)
        if rel.as_posix()=='request-lifecycle.md':continue
        target=RUN/'manuscripts'/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        copied.append(dict(file=rel.as_posix(),sha256=sha(source)))
    # The initial gap assessment still applies to the same published prose.
    baseline=PUBLIC/'publication/issue214/manuscripts/request-lifecycle.md'
    assert split_frontmatter(baseline.read_text(encoding='utf-8'))[1]==split_frontmatter((base.sdd_dir/'request-lifecycle.md').read_text(encoding='utf-8'))[1]
    raw=deepcopy(base.raw)
    generation=yaml.safe_load((RUN/'generation.yaml').read_bytes())
    raw['source']=generation['source'];raw['output']=generation['output']
    for key in ['config','sections_file','scenarios_file','glossary_file','products_file','consistency_file']:
        if key in raw['paths']:
            raw['paths'][key]=str(RUN/'config'/(Path(raw['paths'][key]).name)) if key!='config' else str(RUN/'config')
    raw['visuals']['file']=str(RUN/'config/visuals.yaml')
    raw['products']['file']=str(RUN/'config/products.yaml')
    raw['paths']['translation_profile']=str(RUN/'generation.yaml')
    raw['paths']['consistency_review_config']=str(RUN/'contract-review.yaml')
    raw['publication']['operation_id']='issue252-request-depth'
    inherited=RUN/'inherited-reports';inherited.mkdir()
    for report in raw['publication'].get('reports',[]):
        source=Path(report['path']);assert sha(source)==report['sha256']
        target=inherited/source.name;assert not target.exists();shutil.copyfile(source,target)
        report['path']=str(target);report['producer']='inherited-historical/'+report['producer']
    for page,name in [('default',None),*base.site.manuscript_profiles.items()]:
        chosen=base if name is None else load(base.root/name,manuscript_profile=True)
        style=RUN/'preserved-style'/page.replace('.md','')
        shutil.copytree(chosen.style_dir,style)
        for source in style.glob('*.md'):
            assert sha(source)==manifest['inputs']['editorial/style/'+page+'/'+source.name]
        if name is None:raw['paths']['style']=str(style)
        else:
            target=RUN/('preserved-'+page.replace('/','-')+'.yaml')
            write(target,dict(agent=deepcopy(chosen.raw['agent']),paths=dict(style=str(style))))
            raw['site']['manuscript_profiles'][page]=str(target)
    raw['site']['manuscript_profiles']['request-lifecycle.md']=str(RUN/'request-authentication.yaml')
    raw['site'].update(enabled=False,english_catalog=str(RUN/'english.json'),translation_batch_size=8,
                       mermaid_dir=str(PUBLIC/'docs/assets/mermaid'))
    catalog=Path(base.site.english_catalog)
    assert sha(catalog)==manifest['inputs']['english_catalog']
    shutil.copyfile(catalog,RUN/'english.json')
    write(RUN/'publication.yaml',raw)
    review=deepcopy(raw);review['agent']=generation['agent'];review['agent']['max_input_chars']=180000
    write(RUN/'contract-review.yaml',review)
    # Generation and export share the new base; the selected writer stays unchanged.
    generation['documentation']=deepcopy(raw['documentation'])
    write(RUN/'generation.yaml',generation)
    model=KnowledgeModel.from_dict(theirs) if hasattr(KnowledgeModel,'from_dict') else KnowledgeModel.load(base.facts_path)
    evidence.collect(load(RUN/'generation.yaml'),model)
    model.save(RUN/'facts/facts.json')
    (RUN/'public-base-integration.json').write_text(json.dumps(dict(
        base_build_id=manifest['build_id'],base_profile_sha256=sha(profile),
        original_request_prose_unchanged=True,structural_facts_unchanged=True,
        preserved_manuscripts=copied,scope='Latest published other pages retained; selected request document has its own new CLI generation and audits. Inherited reports retain original scope and bytes.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Latest public base preserved and manifest-bound; final selected generation/reviews still required.',flush=True)


if __name__=='__main__':main()
