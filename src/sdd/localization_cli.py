"""Catalog preparation composition root."""
from pathlib import Path
import json
import hashlib
import html
import re
import os
from .site_localization import source_hash, display_strings, KOREAN
from .execution_lock import locked
from .validation_execution import staged
from .validation_stage import current, load_json, read_bytes
from .state_io import save

def diagram_translation_scopes(directory):
    """Validate and retain each diagram's declared English labels separately."""
    scopes = {}
    def unwrap(value):
        return html.unescape(value.replace('<br/>', '')).strip()
    for path in sorted(directory.rglob('*.mmd')):
        local = {}
        for raw in re.findall(r'^%% sdd:translations (.+)$', path.read_text(encoding='utf-8'), re.M):
            for source, translated in json.loads(raw).items():
                source, translated = unwrap(source), unwrap(translated)
                if not KOREAN.search(source):
                    continue
                if not translated or KOREAN.search(translated):
                    raise ValueError('Diagram label needs an English translation')
                if source in local and local[source] != translated:
                    raise ValueError('Conflicting English translations within the same diagram')
                local[source] = translated
        scopes[path.relative_to(directory).as_posix()] = local
    return scopes


def diagram_translations(directory):
    """Compatibility view of unambiguous labels; never a prose catalog seed."""
    values = {}
    for labels in diagram_translation_scopes(directory).values():
        for source,translated in labels.items():
            values.setdefault(source,set()).add(translated)
    return {source:next(iter(translations)) for source,translations in values.items() if len(translations)==1}

@locked('translation')
@staged
def prepare_catalog(config, destination: Path, *, translate: bool = False, replay_http: bool = False) -> dict:
    """Prepare through the same path in CLI runs and isolated pipeline trials."""
    import copy
    import tempfile
    from .export_site import _render_site
    cfg = copy.deepcopy(config)
    cfg.raw.setdefault('site', {}).pop('english_catalog', None)
    original = read_bytes(destination, optional=True)
    previous = load_json(destination) if original is not None else {}
    cfg.build_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.translation-', dir=cfg.build_dir) as temporary:
        # Private Korean rendering discovers strings for the not-yet-created
        # translation. It is never synchronized to a publication directory.
        # The public export path always checks the completed bilingual review.
        out = _render_site(cfg, Path(temporary), check_consistency=False)
        declared_labels = diagram_translation_scopes(out)
        from .facts.model import KnowledgeModel
        from .translation_context import collect, git_loader
        model = KnowledgeModel.load(cfg.facts_path)
        source_loader = git_loader(cfg.source_root, str(model.meta.get('source_commit', '')))
        contexts, source_contexts = {}, {}
        pages, units = {}, set()
        for path in sorted(out.rglob('*.html')):
            document = path.read_text(encoding='utf-8')
            pages[path.relative_to(out).as_posix()] = source_hash(document)
            units.update(display_strings(document))
            collect(document, model, contexts, source_contexts, source_loader)
        for entry in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
            fields = ('page',) if entry.get('kind') == 'symbol' else ('title', 'page')
            units.update(entry[k].strip() for k in fields if KOREAN.search(entry[k]))
        if (out / 'assets/glossary.json').exists():
            # The in-page term popover reads these names and definitions, so they need translations too.
            for item in json.loads((out / 'assets/glossary.json').read_text(encoding='utf-8')):
                units.update(v.strip() for v in [item['term'], item['definition'], *item['names']] if KOREAN.search(v))
    catalog = {'schema': 1, 'review_status': 'human-review-pending', 'pages': pages,
               'strings': {key: previous.get('strings', {}).get(key, '') for key in sorted(units)}}
    catalog['source_bound_diagram_labels_sha256'] = hashlib.sha256(
        json.dumps(declared_labels,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    catalog.update(source_commit=model.meta['source_commit'],
                   translation_contexts=contexts, source_contexts=source_contexts)
    # Legacy values keep their original status. Once context was recorded, a
    # changed binding/source cannot quietly reuse its previous translation.
    if 'translation_contexts' in previous:
        from .translation_context import unchanged_across_commits, retained_carryover
        carried = set()
        for key in catalog['strings']:
            if previous['translation_contexts'].get(key, []) != contexts.get(key, []):
                if catalog['strings'][key] and unchanged_across_commits(previous, catalog, key):
                    carried.add(hashlib.sha256(key.encode()).hexdigest())
                else:
                    catalog['strings'][key] = ''
        if carried:
            catalog['source_carryover'] = dict(
                from_catalog_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                from_source_commit=previous['source_commit'], to_source_commit=catalog['source_commit'],
                source_string_sha256=sorted(carried),
                translation_sha256={hashlib.sha256(key.encode()).hexdigest():
                    hashlib.sha256(value.encode()).hexdigest() for key, value in catalog['strings'].items()
                    if hashlib.sha256(key.encode()).hexdigest() in carried},
                validation='Every literal source, location, enclosing scope and inline subject is unchanged; commit revalidated.',
                assessment='Historical translations retained; not new inference or human approval.')
        elif previous.get('source_commit') == catalog['source_commit']:
            event = retained_carryover(previous, catalog['strings'])
            if event:
                catalog['source_carryover'] = event
    catalog['legacy_reuse_policy'] = ('Unversioned values require original native-context authentication or retranslation '
        'because old catalogs did not distinguish diagram seeds from prose. Authenticated historical values are not '
        'new inference or human approval. Literal unchanged contexts at a new commit retain their recorded lineage; '
        'changed code, location, scope or subjects require retranslation.')
    catalog['diagram_label_policy'] = 'scoped-proof-v1'
    if 'legacy_diagram_label_revalidation' in previous:
        catalog['legacy_diagram_label_revalidation'] = copy.deepcopy(previous['legacy_diagram_label_revalidation'])
    if previous.get('diagram_label_policy') != catalog['diagram_label_policy']:
        from .translation import fixed_translation
        from .translation_provenance import verified_catalog_units
        selected = cfg.agent
        if cfg.paths.get('translation_profile') is not None:
            from .config import load
            selected = load(cfg.paths['translation_profile']).agent
        authenticated = (verified_catalog_units(selected, previous,
            [cfg.build_dir/'translation-prompts/calls'], batch_only=True,
            instruction_strings=catalog['strings'])
            if selected.kind == 'cli' and selected.model and previous.get('strings') else {})
        invalidated = {hashlib.sha256(key.encode()).hexdigest() for key,value in catalog['strings'].items()
                       if not value and previous.get('strings',{}).get(key)}
        for key,value in catalog['strings'].items():
            # Old catalogs did not identify diagram-seeded values. Authenticate
            # the original CLI context or invalidate; never relabel an unknown
            # old value as a new prose translation under the scoped policy.
            if value and key not in authenticated and fixed_translation(key) != value:
                catalog['strings'][key] = ''
                invalidated.add(hashlib.sha256(key.encode()).hexdigest())
        catalog['legacy_diagram_label_revalidation'] = dict(
            from_catalog_sha256=hashlib.sha256(original).hexdigest() if original is not None else None,
            invalidated_source_sha256=sorted(invalidated),
            original_native_source_sha256=sorted(hashlib.sha256(key.encode()).hexdigest() for key in authenticated),
            assessment='Unversioned diagram seeds cannot approve prose. Reuse requires the selected CLI and current instruction policy; incompatible original calls remain historical, not corrupt or newly approved.')
        if invalidated and 'source_carryover' in catalog:
            from .translation_context import retained_carryover
            retained = retained_carryover(catalog,catalog['strings'])
            if retained:
                catalog['source_carryover'] = retained
            else:
                catalog.pop('source_carryover',None)
    translation_agent = None
    if translate:
        # Rendering can retain the original figure-generation profile while
        # new translations use an independently selected CLI transport.
        profile = config.paths.get('translation_profile')
        if profile is not None:
            from dataclasses import replace
            from .config import load
            cfg = replace(cfg, agent=load(profile).agent)
        from .translation import translate_missing
        if replay_http:
            from .llm import Agent
            from .design_replay import Archive
            directory = cfg.build_dir / 'translation-prompts'
            translation_agent = Archive(directory / 'calls', cfg.agent).reviewer(Agent(cfg.agent, directory))
        catalog = translate_missing(cfg, catalog, translation_agent)
    inputs = current()
    inputs.verify()
    def rollback():
        if original is None:
            destination.unlink(missing_ok=True)
        else:
            destination.write_bytes(original)
    inputs.rollbacks.append(rollback)
    save(destination, catalog)
    expected = (json.dumps(catalog, ensure_ascii=False, indent=2)+'\n').replace('\n', os.linesep).encode('utf-8')
    inputs.produced(destination, expected)
    return {'pages': len(pages), 'strings': len(units),
            'missing_translations': sum(not value for value in catalog['strings'].values()),
            'human_review': 'pending',
            'replayed_http_calls': getattr(translation_agent, 'replayed_http_calls', 0),
            'translation_replays': getattr(translation_agent, 'translation_replays', [])}


def main() -> None:
    """Explicit catalog refresh; new strings remain empty until translated."""
    import argparse
    from .config import load
    parser = argparse.ArgumentParser(description='Prepare an English catalog for translation review')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--translate', action='store_true', help='Translate new text with the configured agent; human review stays pending')
    args = parser.parse_args()
    result = prepare_catalog(load(args.config), args.out, translate=args.translate)
    print(f'Prepared {result["pages"]} pages and {result["strings"]} strings. Review all changed source context before publishing.')
