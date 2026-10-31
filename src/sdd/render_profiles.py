"""Authenticate mixed historical CLI artifacts without executing their runners."""
from dataclasses import replace
from pathlib import PurePosixPath
from .config import load


def paths(cfg):
    values=(cfg.raw.get('site') or {}).get('manuscript_profiles',{})
    if not isinstance(values,dict):
        raise ValueError('site.manuscript_profiles must map Markdown pages to verification profiles')
    for page,name in values.items():
        p=PurePosixPath(page) if isinstance(page,str) else None
        if (p is None or p.is_absolute() or '..' in p.parts or not page.endswith('.md')
                or ':' in page or '\\' in page or not isinstance(name,str) or not name):
            raise ValueError('Invalid manuscript verification profile path')
    return {page:(cfg.root/name).resolve() for page,name in values.items()}


def for_page(cfg,page):
    path=paths(cfg).get(page)
    if path is None:return cfg
    profile=load(path)
    if (set(profile.raw)-{'agent','paths'} or set(profile.raw.get('paths',{}))-{'style'}
            or profile.agent.kind!='cli' or not profile.agent.model or 'style' not in profile.paths):
        raise ValueError('A manuscript verification profile changes only explicit CLI identity and style')
    # Source, facts, section contracts, manuscripts and all validation gates
    # stay with the publication. These fields never authorize model execution.
    return replace(cfg,agent=profile.agent,paths={**cfg.paths,'style':profile.style_dir})


def inputs(cfg):
    from .runtime_evidence import sha256
    result={}
    for name,selected in [('default',cfg),*((page,for_page(cfg,page)) for page in paths(cfg))]:
        if name!='default':result['profile/'+name]=sha256(paths(cfg)[name])
        for style in sorted(selected.style_dir.glob('*.md')):
            result['style/'+name+'/'+style.name]=sha256(style)
    return result
