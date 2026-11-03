"""Render/translate isolated selected pages through production helpers.

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
                             _site_navigation, _prepare_site_pages, source_link_template)
from sdd.localization_cli import diagram_translation_scopes
from sdd.site_localization import display_strings, source_hash, localize_site, KOREAN
from sdd.translation_context import collect, git_loader
from sdd.translation import translate_missing
from sdd.translation import fixed_translation
from sdd.translation_provenance import verified_catalog_units
from sdd.trial_workspace import is_link
from sdd.site_build import verify_site
from preview_search import merge_search

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--public', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--section', action='append', help='Selected section ID; default pipeline-handler')
parser.add_argument('--glossary-only', action='store_true', help='Translate and preview only the common glossary')
parser.add_argument('--include-home', action='store_true', help='Include the actual introductory guide and its separate source-pinned reading map')
parser.add_argument('--previous-catalog', type=Path, help='Reuse an existing native catalog only when source contexts still match')
parser.add_argument('--translation-calls', type=Path, action='append', default=[], help='Additional original native translation calls archives for exact validated reuse')
parser.add_argument('--translation-batch-size', type=int, default=8, help='Execution-local batch size; model and CLI profile remain unchanged')
args = parser.parse_args()
work, public, out = args.work.resolve(), args.public.resolve(), args.out.resolve()
if (out.is_relative_to(public) or public.is_relative_to(out)
        or out.is_relative_to(work) or work.is_relative_to(out)):
    raise ValueError('Preview output must be separate from public inputs and the work root')
if out.exists():
    raise ValueError('Preserve the existing preview and choose a new output')
for artifact in (work/'preview-english.json', work/'preview-translation-plan.json'):
    if artifact.exists() or is_link(artifact) or not artifact.resolve().is_relative_to(work):
        raise ValueError('Preserve the previous catalog/plan and choose a new work root')
cfg = load(work/'generation.yaml')
if not cfg.build_dir.is_relative_to(work):
    raise ValueError('Preview call records and checkpoints must stay inside the isolated work root')
for writable in (work, cfg.build_dir):
    for protected in (public, cfg.source_root):
        if writable.is_relative_to(protected) or protected.is_relative_to(writable):
            raise ValueError('Preview work and build roots must not overlap immutable inputs')
if out.is_relative_to(cfg.source_root) or cfg.source_root.is_relative_to(out):
    raise ValueError('Preview output must be separate from the immutable source checkout')
if (cfg.agent.kind != 'cli' or cfg.agent.runner != 'codex' or cfg.agent.model != 'gpt-6.1-terra'
        or cfg.agent.command or cfg.agent.args != ['-c', 'model_reasoning_effort="high"']):
    raise ValueError('This public translation requires native Codex/Terra High with no inherited wrapper')
settings = deepcopy(load(ROOT/'examples/libcamera/sdd.yaml').raw['site'])
settings.pop('english_catalog', None)
if args.include_home:
    settings['guide_source']['root'] = str((ROOT/'examples/libcamera'/settings['guide_source']['root']).resolve())
    for key in ('intro', 'guide_visuals'):
        name = settings[key]
        target = work/name
        if (not target.resolve().is_relative_to(work) or target.exists() or is_link(target)):
            raise ValueError('Preserve introductory preview inputs: '+str(target))
        shutil.copyfile(ROOT/'examples/libcamera'/name, target)
else:
    for key in ('intro', 'guide_visuals', 'overview_visual'):
        settings.pop(key, None)
if args.translation_batch_size < 1:
    raise ValueError('Translation batch size must be positive')
settings.update(enabled=False, translation_batch_size=args.translation_batch_size)
cfg.raw['site'] = settings
model = KnowledgeModel.load(cfg.facts_path)
sections = {s.get('output', s['id']+'.md'):s for s in cfg.sections()}
texts = {p.relative_to(cfg.sdd_dir).as_posix():p.read_text(encoding='utf-8') for p in cfg.sdd_dir.rglob('*.md')}
terms = glossary.load(cfg)
texts[glossary.PAGE] = glossary.page(terms)
if args.glossary_only and args.section:
    raise ValueError('Select glossary-only or section pages')
selected = [] if args.glossary_only else (args.section or ['pipeline-handler'])
entries = [(s.get('group', 'For Vendor'), s['title'], rel) for rel, s in sections.items() if s['id'] in selected]
if len(entries) != len(set(selected)):
    raise ValueError('Every selected section must exist exactly once')
entries.append(('For Developer', '용어집', glossary.PAGE))
if args.include_home:
    entries.append(('For Developer', '시작', 'index.md'))
ledger = approvals.load(cfg)
states = {rel:approvals.page_status(ledger, rel, texts[rel]) for _,_,rel in entries if rel in texts}
# Use complete navigation in every preview mode, while rendering only selected
# pages. Deferred documents remain byte copies of the public baseline and are
# neither regenerated nor approved here. Home/status use the real composition
# when requested; unselected home text is not written or translated.
selected_paths = {rel for _,_,rel in entries}
sections,navigation_entries = _site_navigation(cfg,cfg.site,set())
texts,states,ledger,terms,model = _prepare_site_pages(
    cfg,cfg.site,sections,navigation_entries,check_consistency=False)
entries = [entry for entry in navigation_entries if entry[2] in selected_paths]

with tempfile.TemporaryDirectory(prefix='.issue215-preview-', dir=work) as temporary:
    stage = Path(temporary).resolve()
    if stage.parent != work:
        raise ValueError('Unexpected preview staging directory')
    class_documents = {rel.removesuffix('.md')+'.html':(public/'docs'/rel.removesuffix('.md')).with_suffix('.html').read_text(encoding='utf-8')
                       for rel,section in sections.items() if section.get('kind')=='per-package'
                       and rel not in {entry[2] for entry in entries}}
    rendered, search, diagrams, visuals = _render_pages(cfg, entries, sections, texts, terms, model,
        cfg.site.source_url, source_link_template(cfg.site),class_documents=class_documents)
    asset_version, terms_version = _write_assets(cfg, stage, None, visuals, terms)
    shutil.copytree(public/'docs/assets/mermaid', stage/'assets/mermaid')
    _write_pages(cfg, stage, navigation_entries, sections, rendered, states, ledger, diagrams,
                 'assets/mermaid/mermaid.esm.min.mjs', title=cfg.site.title,
                 asset_version=asset_version, terms_version=terms_version,
                 selected_pages={rel for _,_,rel in entries})
    _write_search(stage, rendered, search, terms)
    previous_path = args.previous_catalog or public/'publication/issue214/english.json'
    previous = json.loads(previous_path.read_bytes())
    if previous.get('source_commit') != model.meta['source_commit']:
        raise ValueError('Previous translation catalog belongs to another source commit')
    labels = diagram_translation_scopes(stage)
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
    # Record even an empty context explicitly so the next run can distinguish
    # a reviewed context-free string from a catalog without context evidence.
    for key in units:
        contexts.setdefault(key, [])
    strings = {}
    for key in sorted(units):
        value = previous.get('strings', {}).get(key, '')
        if (key not in previous.get('translation_contexts', {})
                or previous['translation_contexts'][key] != contexts.get(key, [])):
            value = ''
        strings[key] = value
    catalog = dict(schema=1, review_status='human-review-pending', pages=pages, strings=strings,
                   diagram_label_policy='scoped-proof-v1',
                   source_commit=model.meta['source_commit'], translation_contexts=contexts, source_contexts=pool,
                   scope='Isolated selected-page/glossary preview; not whole-site acceptance')
    archives = list(args.translation_calls)
    if previous_path.with_name('generation.yaml').is_file():
        archives.append(load(previous_path.with_name('generation.yaml')).build_dir/'translation-prompts/calls')
    previous_proof = verified_catalog_units(cfg.agent, catalog, archives, batch_only=True)
    candidates = verified_catalog_units(cfg.agent, catalog, archives, allow_other_values=True, batch_only=True)
    for key, proof in candidates.items():
        if key not in previous_proof:
            strings[key] = proof['reused_value']
            previous_proof[key] = proof
    for key in strings:
        if key not in previous_proof and fixed_translation(key) != strings[key]:
            strings[key] = ''
    catalog_path = work/'preview-english.json'
    if catalog_path.exists():
        raise ValueError('Preserve the previous catalog and use a new work root for another preview')
    (work/'preview-translation-plan.json').write_text(json.dumps(dict(
        pages=list(pages), strings=len(strings), missing=sum(not v for v in strings.values()),
        previous_catalog_sha256=hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        verified_reuse=previous_proof,
        translation_batch_size=cfg.site.translation_batch_size,
        agent=dict(kind=cfg.agent.kind, runner=cfg.agent.runner, model=cfg.agent.model,
                   command=cfg.agent.command, args=cfg.agent.args)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    catalog = translate_missing(cfg, catalog)
    provenance = verified_catalog_units(cfg.agent, catalog, [*archives, cfg.build_dir/'translation-prompts/calls'])
    if any(fixed_translation(key) != value and key not in provenance
           for key,value in catalog['strings'].items()):
        raise ValueError('Translation lacks completed native Codex/Terra High provenance; previous outputs preserved')
    catalog['native_translation_provenance'] = provenance
    catalog['source_bound_diagram_labels_sha256'] = hashlib.sha256(
        json.dumps(labels, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    cfg.raw['site']['english_catalog'] = str(catalog_path)
    localize_site(cfg, stage)
    merge_search(public/'docs', stage, {rel for _,_,rel in entries})
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
    changed = [rel.removesuffix('.md')+'.html' for _, _, rel in entries]
    changed += ['en/'+name for name in changed.copy()]
    report = dict(scope='Preview only; not publication or full-site visual acceptance',
        source_commit=model.meta['source_commit'], human_review='pending', verification=result,
        changed_pages=changed,
        html_sha256={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in changed})
    (out/'preview-scope.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
