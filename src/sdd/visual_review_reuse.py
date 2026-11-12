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
    Document, REPORT, all_nodes, apply_reviews, canonical, enforce, inspect_site, policy,
)


def indexed(report):
    return {row['id']: row for row in report['items']}


def carry_reviews(ledger, previous, current, previous_relative, current_relative, *, baseline_build, stable_pages,
                  source_proof=None, trace_proofs=None):
    before, after = indexed(previous), indexed(current)
    relative_before, relative_after = indexed(previous_relative), indexed(current_relative)

    def equivalent(key):
        old, new = before.get(key), after.get(key)
        if old is None or new is None or new['page'] not in stable_pages:
            return False
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
        if source_proof is not None:
            candidate['source_reuse'] = dict(
                schema=1, baseline_build_id=baseline_build,
                previous_commit=source_proof.previous_commit, current_commit=source_proof.current_commit,
                previous_fingerprint=old['fingerprint'], comparison_fingerprint=relative_after[key]['fingerprint'],
                **trace_proofs[key],
            )
            if adjacent:
                candidate['source_reuse']['adjacent_comparison_fingerprint'] = relative_after[adjacent]['fingerprint']
        elif record != candidate:
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
        method = 'source_revision' if source_proof is not None else 'position_only' if candidate != ledger['items'][key] else 'exact'
        counts[method] += 1
    pending = sorted(set(after) - set(kept))
    return {**ledger, 'items': kept}, dict(
        baseline_build_id=baseline_build, exact=counts['exact'], position_only=counts['position_only'],
        source_revision=counts['source_revision'], pending=pending, deleted=sorted(set(before) - set(after)),
    )


def presentation_environment(root, page):
    document = Document(owned_path(root, page).read_text(encoding='utf-8'))
    return [(node.tag, node.attrs) if node.tag in {'html', 'body'} else canonical(node)
            for node in all_nodes(document.root)
            if node.tag in {'html', 'body', 'base', 'style', 'script', 'link'}]


def reuse_published(baseline, current, reviews, options, *, source_commit, source_root=None, source_settings=None):
    previous_manifest = load_json(baseline / MANIFEST)
    current_manifest = load_json(current / MANIFEST)
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

    updated, report = carry_reviews(ledger, published, new, comparison_report(baseline, previous_manifest, previous_commit),
                                   comparison_report(current, current_manifest, source_commit),
                                   baseline_build=previous_manifest['build_id'], stable_pages=stable_pages,
                                   source_proof=source_proof, trace_proofs=traces)
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
    args = parser.parse_args()
    from .config import load
    cfg = load(args.config)
    ledger, report = reuse_published(args.baseline, args.site, args.reviews, policy(cfg),
                                    source_commit=args.source_commit, source_root=cfg.source_root,
                                    source_settings=cfg.site)
    args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
