"""Catalog preparation composition root."""
from pathlib import Path
import json
from .site_localization import source_hash, display_strings, KOREAN

def main() -> None:
    """Explicit catalog refresh; new strings remain empty until translated."""
    import argparse
    import copy
    import tempfile
    from .config import load
    from .export_site import _render_site
    parser = argparse.ArgumentParser(description='Prepare an English catalog for translation review')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = copy.deepcopy(load(args.config))
    cfg.raw.setdefault('site', {}).pop('english_catalog', None)
    previous = json.loads(args.out.read_text(encoding='utf-8')) if args.out.exists() else {}
    cfg.build_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.translation-', dir=cfg.build_dir) as temporary:
        out = _render_site(cfg, Path(temporary))
        pages, units = {}, set()
        for path in sorted(out.rglob('*.html')):
            document = path.read_text(encoding='utf-8')
            pages[path.relative_to(out).as_posix()] = source_hash(document)
            units.update(display_strings(document))
        for entry in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
            units.update(entry[k].strip() for k in ('title', 'page') if KOREAN.search(entry[k]))
    catalog = {'schema': 1, 'review_status': 'human-review-pending', 'pages': pages,
               'strings': {key: previous.get('strings', {}).get(key, '') for key in sorted(units)}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(pages)} pages and {len(units)} strings. Review all changed source context before publishing.')
