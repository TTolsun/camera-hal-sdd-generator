"""Catalog preparation composition root."""
from pathlib import Path
import json
import html
import re
from .site_localization import source_hash, display_strings, KOREAN

def diagram_translations(directory):
    """Keep visible labels consistent with the graph's declared English edition."""
    values = {}
    def unwrap(value):
        return html.unescape(value.replace('<br/>', '')).strip()
    for path in sorted(directory.rglob('*.mmd')):
        for raw in re.findall(r'^%% sdd:translations (.+)$', path.read_text(encoding='utf-8'), re.M):
            for source, translated in json.loads(raw).items():
                source, translated = unwrap(source), unwrap(translated)
                if not KOREAN.search(source):
                    continue
                if not translated or KOREAN.search(translated):
                    raise ValueError('Diagram label needs an English translation')
                if source in values and values[source] != translated:
                    raise ValueError('Conflicting English translations for the same diagram label')
                values[source] = translated
    return values

def prepare_catalog(config, destination: Path, *, translate: bool = False) -> dict:
    """Prepare through the same path in CLI runs and isolated pipeline trials."""
    import copy
    import tempfile
    from .export_site import _render_site
    cfg = copy.deepcopy(config)
    cfg.raw.setdefault('site', {}).pop('english_catalog', None)
    previous = json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else {}
    cfg.build_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.translation-', dir=cfg.build_dir) as temporary:
        out = _render_site(cfg, Path(temporary))
        declared_labels = diagram_translations(out)
        pages, units = {}, set()
        for path in sorted(out.rglob('*.html')):
            document = path.read_text(encoding='utf-8')
            pages[path.relative_to(out).as_posix()] = source_hash(document)
            units.update(display_strings(document))
        for entry in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
            units.update(entry[k].strip() for k in ('title', 'page') if KOREAN.search(entry[k]))
        if (out / 'assets/glossary.json').exists():
            # The in-page term popover reads these names and definitions, so they need translations too.
            for item in json.loads((out / 'assets/glossary.json').read_text(encoding='utf-8')):
                units.update(v.strip() for v in [item['term'], item['definition'], *item['names']] if KOREAN.search(v))
    catalog = {'schema': 1, 'review_status': 'human-review-pending', 'pages': pages,
               'strings': {key: declared_labels.get(key, previous.get('strings', {}).get(key, '')) for key in sorted(units)}}
    if translate:
        from .translation import translate_missing
        catalog = translate_missing(cfg, catalog)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'pages': len(pages), 'strings': len(units),
            'missing_translations': sum(not value for value in catalog['strings'].values()),
            'human_review': 'pending'}


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
