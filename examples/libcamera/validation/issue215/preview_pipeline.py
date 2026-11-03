"""Render/translate an isolated two-page preview through production helpers.

This is a UI preview, not a full-site publication or an acceptance bypass.
The public checkout and original runtime/approval records remain untouched.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from sdd.config import load
from sdd.facts.model import KnowledgeModel
from sdd import glossary, approvals
from sdd.export_site import (_render_pages, _write_assets, _write_pages, _write_search,
                             source_link_template)
from sdd.localization_cli import diagram_translations
from sdd.site_localization import display_strings, source_hash, localize_site, KOREAN
from sdd.translation_context import collect, git_loader
from sdd.translation import translate_missing
from sdd.site_build import verify_site

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--public', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
work, public, out = args.work.resolve(), args.public.resolve(), args.out.resolve()
if out.exists():
    raise ValueError('Preserve the existing preview and choose a new output')
cfg = load(work/'generation.yaml')
settings = deepcopy(load(ROOT/'examples/libcamera/sdd.yaml').raw['site'])
settings.pop('intro', None)
settings.pop('english_catalog', None)
settings.pop('overview_visual', None)
settings.update(enabled=False, translation_batch_size=8)
cfg.raw['site'] = settings
model = KnowledgeModel.load(cfg.facts_path)
sections = {s.get('output', s['id']+'.md'):s for s in cfg.sections()}
texts = {p.relative_to(cfg.sdd_dir).as_posix():p.read_text(encoding='utf-8') for p in cfg.sdd_dir.rglob('*.md')}
terms = glossary.load(cfg)
texts[glossary.PAGE] = glossary.page(terms)
entries = [(sections['pipeline-handler.md'].get('group', 'For Vendor'), sections['pipeline-handler.md']['title'], 'pipeline-handler.md'),
           ('For Developer', '용어집', glossary.PAGE)]
ledger = approvals.load(cfg)
states = {rel:approvals.page_status(ledger, rel, texts[rel]) for _,_,rel in entries}

with tempfile.TemporaryDirectory(prefix='.issue215-preview-', dir=work) as temporary:
    stage = Path(temporary).resolve()
    if stage.parent != work:
        raise ValueError('Unexpected preview staging directory')
    rendered, search, diagrams, visuals = _render_pages(cfg, entries, sections, texts, terms, model,
                                                       cfg.site.source_url, source_link_template(cfg.site))
    asset_version, terms_version = _write_assets(cfg, stage, None, visuals, terms)
    shutil.copytree(public/'docs/assets/mermaid', stage/'assets/mermaid')
    _write_pages(cfg, stage, entries, sections, rendered, states, ledger, diagrams,
                 'assets/mermaid/mermaid.esm.min.mjs', title=cfg.site.title,
                 asset_version=asset_version, terms_version=terms_version)
    _write_search(stage, rendered, search, terms)
    previous = json.loads((public/'publication/issue214/english.json').read_bytes())
    labels = diagram_translations(stage)
    contexts, pool, pages, units = {}, {}, {}, set()
    loader = git_loader(cfg.source_root, model.meta['source_commit'])
    for path in stage.rglob('*.html'):
        document = path.read_text(encoding='utf-8')
        pages[path.relative_to(stage).as_posix()] = source_hash(document)
        units.update(display_strings(document))
        collect(document, model, contexts, pool, loader)
    for entry in json.loads((stage/'assets/search.json').read_bytes()):
        for key in ('page',) if entry.get('kind') == 'symbol' else ('title', 'page'):
            if KOREAN.search(entry[key]):
                units.add(entry[key].strip())
    for term in json.loads((stage/'assets/glossary.json').read_bytes()):
        units.update(value.strip() for value in [term['term'], term['definition'], *term['names']] if KOREAN.search(value))
    strings = {}
    for key in sorted(units):
        value = labels.get(key, previous.get('strings', {}).get(key, ''))
        if (key not in labels and 'translation_contexts' in previous
                and previous['translation_contexts'].get(key, []) != contexts.get(key, [])):
            value = ''
        strings[key] = value
    catalog = dict(schema=1, review_status='human-review-pending', pages=pages, strings=strings,
                   source_commit=model.meta['source_commit'], translation_contexts=contexts, source_contexts=pool,
                   scope='Isolated pipeline/glossary preview; not whole-site acceptance')
    catalog_path = work/'preview-english.json'
    if catalog_path.exists():
        raise ValueError('Preserve the previous catalog and use a new work root for another preview')
    (work/'preview-translation-plan.json').write_text(json.dumps(dict(
        pages=list(pages), strings=len(strings), missing=sum(not v for v in strings.values()),
        agent=dict(kind=cfg.agent.kind, runner=cfg.agent.runner, model=cfg.agent.model,
                   command=cfg.agent.command, args=cfg.agent.args)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    catalog = translate_missing(cfg, catalog)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    cfg.raw['site']['english_catalog'] = str(catalog_path)
    localize_site(cfg, stage)
    shutil.copytree(public/'docs', out)
    # A mixed preview must never retain the baseline's publication identity.
    (out/'site-manifest.json').unlink()
    for path in stage.rglob('*'):
        if path.is_file():
            relative = path.relative_to(stage)
            target = (out/relative).resolve()
            if not target.is_relative_to(out):
                raise ValueError('Unsafe preview output path')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    result = verify_site(out, manifest=False)
    report = dict(scope='Preview only; not publication or full-site visual acceptance',
        source_commit=model.meta['source_commit'], human_review='pending', verification=result,
        changed_pages=['pipeline-handler.html', 'en/pipeline-handler.html', 'glossary.html', 'en/glossary.html'],
        html_sha256={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['pipeline-handler.html','en/pipeline-handler.html']})
    (out/'preview-scope.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
