"""Carry published judgments when position or source revision changes are proved equivalent."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .site_build import MANIFEST, verify_site
from .site_paths import owned_path
from .validation_stage import load_json
from .visual_audit import (
    Document, Node, REPORT, all_nodes, apply_reviews, canonical, enforce, inspect_site, policy,
)

# Generator-owned lines inside source-excerpt and diagram notes. Their wording
# changes with site presentation and with each translation, never with an
# item's explanation, figure or source. Comparing them would send every item
# with an excerpt back to review after a pure label change.
#
# A line is normalized only when its complete text is one of the exact forms
# the generator (Korean) or that build's English catalog (English) produces.
# The excerpt start citation and end line are kept in the normalized token,
# so a changed range, added prose or edited translation still differs.
PRESENTATION_NORMALIZATION = 'generator-note-labels-v3'
_EXCERPT_TITLES = {'소스 근거: ': 'source', 'Source evidence: ': 'source', '제품 자료: ': 'product',
                   'Product evidence: ': 'product', 'Product material: ': 'product',
                   '커밋 기록: ': 'commit', 'Commit record: ': 'commit'}
_SCOPE_TITLES = {'그림 근거와 확인 범위', 'Diagram evidence and verification scope'}
_LEGACY_EXCERPT_KEY = '{{0}}에서 시작하는 발췌입니다. 종료 줄은 {end}이며, 아래 원문을 설명과 대조할 수 있습니다.'
_RANGE_KEY = '발췌 범위: {{1}} ~ {{3}}'


def _excerpt_end(text, location, english, catalog):
    """End line of an exact generated location line, or None."""
    import re
    from .reading_cleanup import EXCERPT_RANGE_LABEL
    from .translation import fixed_translation
    if not english:
        for pattern in (re.escape(location) + r'에서 시작하는 발췌입니다\. 종료 줄은 (\d+)이며, '
                                              r'아래 원문을 설명과 대조할 수 있습니다\.',
                        re.escape(EXCERPT_RANGE_LABEL) + ' ' + re.escape(location) + r' ~ (\d+)'):
            if match := re.fullmatch(pattern, text):
                return match[1]
        return None
    for end in sorted(set(re.findall(r'\d+', text))):
        legacy = catalog.get(_LEGACY_EXCERPT_KEY.replace('{end}', end))
        if legacy and legacy.replace('{{0}}', location) == text:
            return end
        label = catalog.get(_RANGE_KEY) or fixed_translation(_RANGE_KEY)
        if label and label.replace('{{1}}', location).replace('{{3}}', end) == text:
            return end
    return None


def _scope_lines(english, catalog):
    from .reading_cleanup import VISUAL_SCOPE_LABEL, VISUAL_SCOPE_SENTENCE
    from .translation import fixed_translation
    if not english:
        return {VISUAL_SCOPE_SENTENCE, VISUAL_SCOPE_LABEL}
    return {value for value in (catalog.get(VISUAL_SCOPE_SENTENCE), catalog.get(VISUAL_SCOPE_LABEL),
                                fixed_translation(VISUAL_SCOPE_LABEL)) if value}


def _download_menu(node, page):
    """Remove only known generator menus from the review comparison."""
    from .full_document import LABELS, _menu, paths
    if node.tag != 'nav' or node.attrs.get('class') != 'download-nav':
        return False
    links = list(node.all('a'))
    if len(links) in (2, 4) and list(node.all('button')):
        filename = links[-1].attrs.get('download', '')
        if not filename.endswith('.md'):
            return False
        expected = Document(_menu(page, page.startswith('en/'), filename, whole_only=len(links) == 2,
                                  pdf_downloads=len(links) == 4 and 'download' in links[0].attrs))
        return node == next(expected.root.all('nav'))

    # Previously published sites used a details disclosure with a text arrow.
    children = [child for child in node.children if not (isinstance(child, str) and not child.strip())]
    if len(children) != 1 or not isinstance(children[0], Node):
        return False
    details = children[0]
    if details.tag != 'details' or details.attrs.get('class') != 'language-selector download-menu':
        return False
    parts = [child for child in details.children if not (isinstance(child, str) and not child.strip())]
    if (len(parts) != 2 or not all(isinstance(part, Node) for part in parts)
            or [part.tag for part in parts] != ['summary', 'nav']):
        return False
    summary, links = parts
    labels = {'⤓ ▾'}
    anchors = [child for child in links.children if isinstance(child, Node)]
    if (summary.text() not in labels or any(isinstance(child, str) and child.strip() for child in links.children)
            or len(anchors) != 2 or any(anchor.tag != 'a' or list(anchor.all('a'))[1:] for anchor in anchors)):
        return False
    print_page, markdown_file = paths(False)
    pdf, markdown = anchors
    return (pdf.text() in {label['pdf'] for label in LABELS.values()}
            and markdown.text() in {label['markdown'] for label in LABELS.values()}
            and set(pdf.attrs) == {'href'} and set(markdown.attrs) == {'href', 'download'}
            and pdf.attrs['href'].endswith(print_page + '?print')
            and markdown.attrs['href'].endswith(markdown_file)
            and markdown.attrs['download'].endswith('.md'))


def presentation_normalizer(catalog=None):
    """Comparison transform; ``catalog`` is the English catalog the site was built with."""
    strings = (catalog or {}).get('strings', {})

    def normalize(document, page, root=None):
        # The whole-document Download menu is page chrome added to every page; it carries no
        # explanation, figure or source. Remove it only in the generator's exact form.
        for actions in document.root.all('div'):
            if actions.attrs.get('class') == 'header-actions':
                actions.children = [child for child in actions.children
                                    if not (isinstance(child, Node) and _download_menu(child, page))]
        english = page.startswith('en/')
        if english and not strings:
            return  # Without the build's catalog no English line can be proved generated.
        scope_lines = _scope_lines(english, strings)
        for details in document.root.all('details'):
            if 'note' not in details.attrs.get('class', '').split():
                continue
            nodes = [child for child in details.children if isinstance(child, Node)]
            if not nodes or nodes[0].tag != 'summary':
                continue
            title = nodes[0].text().strip()
            paragraphs = [node for node in nodes[1:] if node.tag == 'p']
            prefix = next((p for p in _EXCERPT_TITLES if title.startswith(p)), None)
            if prefix is not None:
                location = title[len(prefix):]
                # Product material puts a provenance notice before the location line.
                for line in paragraphs[:2]:
                    cited = [child for child in line.children if isinstance(child, Node)
                             and any(code.text() == location
                                     for code in ([child] if child.tag == 'code' else list(child.all('code'))))]
                    end = _excerpt_end(line.text().strip(), location, english, strings) if len(cited) == 1 else None
                    if end is not None:
                        line.children = ['[excerpt location] ', cited[0], f' [end {end}]']
                        nodes[0].children = [f'[{_EXCERPT_TITLES[prefix]} excerpt] {location}']
                        break
            elif title in _SCOPE_TITLES and len(paragraphs) >= 2 and paragraphs[1].text().strip() in scope_lines:
                paragraphs[1].children = ['[diagram scope]']

    return normalize


# Korean-only comparison, for callers without an English catalog.
normalize_presentation = presentation_normalizer()


def indexed(report):
    return {row['id']: row for row in report['items']}


def carry_reviews(ledger, previous, current, previous_relative, current_relative, *, baseline_build, stable_pages,
                  source_proof=None, trace_proofs=None, presentation=None):
    before, after = indexed(previous), indexed(current)
    relative_before, relative_after = indexed(previous_relative), indexed(current_relative)
    labeled_before, labeled_after = (indexed(presentation[0]), indexed(presentation[1])) if presentation else ({}, {})

    def label_only(key):
        """The same absolute item once generator note labels are normalized on both sides."""
        old, new = labeled_before.get(key), labeled_after.get(key)
        return (old is not None and new is not None and before[key]['fingerprint'] != after[key]['fingerprint']
                and old['fingerprint'] == new['fingerprint'])

    def equivalent(key):
        old, new = before.get(key), after.get(key)
        if old is None or new is None or new['page'] not in stable_pages:
            return False
        if source_proof is None and label_only(key):
            return True
        if source_proof is not None:
            return (key in trace_proofs and key in relative_before and key in relative_after
                    and relative_before[key]['fingerprint'] == relative_after[key]['fingerprint'])
        if old['fingerprint'] == new['fingerprint']:
            return True
        return (bool(old['anchor']) and old['anchor'] == new['anchor']
                and key in relative_before and key in relative_after
                and relative_before[key]['fingerprint'] == relative_after[key]['fingerprint'])

    kept, counts = {}, Counter()
    for key, record in ledger['items'].items():
        if not equivalent(key):
            continue
        adjacent = record.get('adjacent_item')
        if adjacent and not equivalent(adjacent):
            continue
        old, new = before[key], after[key]
        candidate = {**record, 'fingerprint': new['fingerprint']}
        if adjacent:
            candidate['adjacent_fingerprint'] = after[adjacent]['fingerprint']
        if old['fingerprint'] != new['fingerprint']:
            # Provenance describes this carry; an earlier carry's method no longer applies.
            for field in ('presentation_reuse', 'position_reuse', 'source_reuse'):
                candidate.pop(field, None)
        if source_proof is not None:
            candidate['source_reuse'] = dict(
                schema=1, baseline_build_id=baseline_build,
                previous_commit=source_proof.previous_commit, current_commit=source_proof.current_commit,
                previous_fingerprint=old['fingerprint'], comparison_fingerprint=relative_after[key]['fingerprint'],
                **trace_proofs[key],
            )
            if adjacent:
                candidate['source_reuse']['adjacent_comparison_fingerprint'] = relative_after[adjacent]['fingerprint']
        elif label_only(key):
            candidate['presentation_reuse'] = dict(
                schema=1, baseline_build_id=baseline_build, normalization=PRESENTATION_NORMALIZATION,
                previous_fingerprint=old['fingerprint'], normalized_fingerprint=labeled_after[key]['fingerprint'],
            )
            if adjacent:
                candidate['presentation_reuse']['adjacent_normalized_fingerprint'] = labeled_after[adjacent]['fingerprint']
        elif old['fingerprint'] != new['fingerprint']:
            candidate['position_reuse'] = dict(
                schema=1, baseline_build_id=baseline_build,
                previous_fingerprint=old['fingerprint'],
                section_relative_fingerprint=relative_after[key]['fingerprint'],
            )
            if adjacent:
                candidate['position_reuse']['adjacent_section_relative_fingerprint'] = relative_after[adjacent]['fingerprint']
        kept[key] = candidate

    # A neighbor can remain equivalent while a new sibling breaks adjacency.
    # Run the same acceptance checks used at publication before returning it.
    apply_reviews(current, {'schema': 1, 'items': kept})
    for key, candidate in list(kept.items()):
        if after[key]['status'] != candidate['status']:
            del kept[key]
            continue
        # Decide from this run's comparison, never from provenance copied out of the ledger.
        method = ('source_revision' if source_proof is not None
                  else 'exact' if before[key]['fingerprint'] == after[key]['fingerprint']
                  else 'presentation_only' if label_only(key) else 'position_only')
        counts[method] += 1
    pending = sorted(set(after) - set(kept))
    return {**ledger, 'items': kept}, dict(
        baseline_build_id=baseline_build, exact=counts['exact'], position_only=counts['position_only'],
        presentation_only=counts['presentation_only'], source_revision=counts['source_revision'],
        pending=pending, deleted=sorted(set(before) - set(after)),
    )


def presentation_environment(root, page):
    document = Document(owned_path(root, page).read_text(encoding='utf-8'))
    return [(node.tag, node.attrs) if node.tag in {'html', 'body'} else canonical(node)
            for node in all_nodes(document.root)
            if node.tag in {'html', 'body', 'base', 'style', 'script', 'link'}]


def _catalog(path, manifest, side):
    """The English catalog a site was built with, proved by its manifest input."""
    if path is None:
        return None
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.get('inputs', {}).get('english_catalog'):
        raise ValueError(f'{side} English catalog does not match its site manifest')
    return json.loads(data)


def reuse_published(baseline, current, reviews, options, *, source_commit, source_root=None, source_settings=None,
                    baseline_catalog=None, current_catalog=None):
    previous_manifest = load_json(baseline / MANIFEST)
    current_manifest = load_json(current / MANIFEST)
    catalogs = (_catalog(baseline_catalog, previous_manifest, 'Baseline'),
                _catalog(current_catalog, current_manifest, 'Current'))
    verify_site(baseline)
    verify_site(current)
    if hashlib.sha256(reviews.read_bytes()).hexdigest() != previous_manifest['inputs'].get('item_visual_reviews'):
        raise ValueError('Baseline reviews do not match the published manifest')
    published = load_json(baseline / REPORT)
    previous_commit = published['source_commit']
    if not source_commit or not previous_commit:
        raise ValueError('Visualization reuse requires pinned source commits')
    source_proof = None
    if previous_commit != source_commit:
        if source_root is None or source_settings is None:
            raise ValueError('Different visualization source commits require immutable Git source proof')
        from .visual_source_reuse import SourceProof
        source_proof = SourceProof(source_root, source_settings, previous_commit, source_commit)
    for key in ('thresholds', 'signals', 'style_policy', 'deferred_pages'):
        if published['policy'][key] != options[key]:
            raise ValueError('Position reuse requires the same visual policy: ' + key)
    if published['policy'].get('require_provenance', False) != options.get('require_provenance', False):
        raise ValueError('Position reuse requires the same visual policy: require_provenance')

    def assets(manifest):
        return {path: sha for path, sha in manifest['outputs'].items()
                if Path(path).suffix.lower() in {'.css', '.js', '.mjs'}}

    ledger = load_json(reviews)
    apply_reviews(published, ledger)
    enforce(published)
    new = inspect_site(current, options, manifest=current_manifest, source_commit=source_commit)
    stable_pages = set()
    if (assets(previous_manifest) == assets(current_manifest) and
            (source_proof is None or previous_manifest.get('dependencies') == current_manifest.get('dependencies'))):
        stable_pages = {page for page in set(published['pages']) & set(new['pages'])
                        if (previous_manifest['outputs'][page] == current_manifest['outputs'][page]
                            or presentation_environment(baseline, page) == presentation_environment(current, page))}
    before, after = indexed(published), indexed(new)
    moved_pages = {after[key]['page'] for key in before.keys() & after.keys()
                   if after[key]['page'] in stable_pages and before[key]['fingerprint'] != after[key]['fingerprint']}

    def comparison_report(root, manifest, commit):
        selected = {'outputs': {page: manifest['outputs'][page] for page in moved_pages}}
        transform = None if source_proof is None else lambda doc, page, root: source_proof.normalize(doc, commit, page, root)
        return inspect_site(root, options, manifest=selected, source_commit=commit,
                            section_relative=source_proof is None, comparison_transform=transform,
                            comparison_commit=previous_commit if source_proof is not None else None)

    traces = None
    if source_proof is not None:
        from .visual_source_reuse import trace_proof
        traces = {}
        for key, record in ledger['items'].items():
            if key not in after or after[key]['page'] not in stable_pages:
                continue
            if source_proof.additional_sources_unchanged(record):
                checked = trace_proof(record, baseline, current, after[key]['page'], previous_commit, source_commit)
                if checked is not None:
                    traces[key] = checked

    # Presentation normalization is not combined with a source revision: both
    # changing at once leaves the item pending, the conservative outcome.
    presentation = None
    if source_proof is None:
        def labeled(root, manifest, catalog):
            selected = {'outputs': {page: manifest['outputs'][page] for page in moved_pages}}
            return inspect_site(root, options, manifest=selected, source_commit=source_commit,
                                comparison_transform=presentation_normalizer(catalog))
        presentation = (labeled(baseline, previous_manifest, catalogs[0]),
                        labeled(current, current_manifest, catalogs[1]))
    updated, report = carry_reviews(ledger, published, new, comparison_report(baseline, previous_manifest, previous_commit),
                                   comparison_report(current, current_manifest, source_commit),
                                   baseline_build=previous_manifest['build_id'], stable_pages=stable_pages,
                                   source_proof=source_proof, trace_proofs=traces, presentation=presentation)
    if source_proof is not None:
        report['source_proof'] = dict(previous_commit=previous_commit, current_commit=source_commit,
            files=[dict(commit=commit, path=path, sha256=checksum)
                   for (commit, path), checksum in sorted(source_proof.checked.items())])
    return updated, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--reviews', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline-catalog', type=Path,
                        help='English catalog the baseline site was built with (checked against its manifest)')
    parser.add_argument('--current-catalog', type=Path,
                        help='English catalog the current site was built with (checked against its manifest)')
    args = parser.parse_args()
    from .config import load
    cfg = load(args.config)
    ledger, report = reuse_published(args.baseline, args.site, args.reviews, policy(cfg),
                                    source_commit=args.source_commit, source_root=cfg.source_root,
                                    source_settings=cfg.site, baseline_catalog=args.baseline_catalog,
                                    current_catalog=args.current_catalog)
    args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
