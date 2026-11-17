"""Measure what a candidate generator would send back to a model on a published input.

The publication gates trust cached judgments only while the bytes they were
computed from are unchanged: translation keys, item visual review
fingerprints and contract audit checkpoints. A generator change that looks
cosmetic can invalidate hundreds of them, and the cost only shows up when the
public site is rebuilt after merge. ``replay`` rebuilds the same published
input with the current code before merge and counts that work without
calling a model.

It never writes into the publication directory, the review ledger, the
English catalog or the audit checkpoints. Everything it produces is under
``out``. Counts are estimates of model work, not review results.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from .validation_stage import load_json

SCHEMA = 1
PLACEHOLDER = '[replay: translation required]'


# The preview disables the item visual gate, so its report and inputs are
# absent by construction. Listing them as removals would hide real ones.
PREVIEW_OMITTED_OUTPUTS = {'item-visual-audit.json'}
PREVIEW_OMITTED_INPUTS = ('item_visual_', 'configuration', 'english_catalog')


def manifest_delta(baseline: dict, current: dict) -> dict:
    before, after = baseline.get('outputs', {}), current.get('outputs', {})
    inputs = sorted(k for k in baseline.get('inputs', {}).keys() | current.get('inputs', {}).keys()
                    if baseline.get('inputs', {}).get(k) != current.get('inputs', {}).get(k))
    removed = sorted(before.keys() - after.keys())
    return dict(
        changed=sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        added=sorted(after.keys() - before.keys()),
        removed=[k for k in removed if k not in PREVIEW_OMITTED_OUTPUTS],
        inputs_changed=[k for k in inputs if not k.startswith(PREVIEW_OMITTED_INPUTS)],
        preview_omitted=dict(outputs=[k for k in removed if k in PREVIEW_OMITTED_OUTPUTS],
                             inputs=[k for k in inputs if k.startswith(PREVIEW_OMITTED_INPUTS)]),
    )


def translation_need(cfg, scratch_catalog: Path) -> dict:
    """Refresh a copy of the catalog and count strings no rule can fill."""
    from .localization_cli import prepare_catalog
    from .translation import fixed_translation
    configured = cfg.site.english_catalog
    if configured is None:
        return dict(enabled=False)
    source = cfg.root / configured
    if source.is_file():
        shutil.copyfile(source, scratch_catalog)
    prepare_catalog(cfg, scratch_catalog)
    catalog = load_json(scratch_catalog)
    strings = catalog['strings']
    fixed = [key for key, value in strings.items() if not value and fixed_translation(key)]
    model = sorted(key for key, value in strings.items() if not value and not fixed_translation(key))
    for key in fixed:
        strings[key] = fixed_translation(key)
    # Only so the private preview can render English pages; never published.
    for key in model:
        strings[key] = PLACEHOLDER
    scratch_catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return dict(enabled=True, strings=len(strings), fixed_fill=len(fixed), model_required=len(model),
                model_required_sample=model[:20])


def contract_plan(cfg, model) -> dict:
    """Count contract audit batches that have no reusable checkpoint."""
    from .consistency import SYSTEM, batches, groups, identity, request, review_store, _review_config
    from .consistency_profile import resolve
    configured = groups(cfg)
    if not configured:
        return dict(enabled=False)
    review = _review_config(resolve(cfg, model, groups, identity, request))
    fresh = reused = 0
    fresh_chars = 0
    for group in configured:
        payload = request(review, model, group)
        for batch in batches(payload, size=review.review.contract_batch_size,
                             max_input_chars=review.agent.max_input_chars):
            store, request_data = review_store(review, batch)
            if store.read() is None:
                fresh += 1
                fresh_chars += len(SYSTEM) + len(request_data['user'])
            else:
                reused += 1
    return dict(enabled=True, batches=fresh + reused, reused=reused, fresh=fresh, fresh_input_chars=fresh_chars)


def _published_catalog(cfg, baseline: Path):
    """The configured catalog, only when it is the one the baseline was built with."""
    import hashlib
    if cfg.site.english_catalog is None:
        return None
    path = cfg.root / cfg.site.english_catalog
    expected = load_json(baseline / 'site-manifest.json').get('inputs', {}).get('english_catalog')
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return path
    return None


def visual_plan(cfg, baseline: Path, site: Path, retained: Path, current_catalog: Path | None) -> dict:
    from .visual_audit import policy
    from .visual_review_reuse import reuse_published
    options = policy(cfg)
    if not options.get('enabled', False) or not options.get('reviews'):
        return dict(enabled=False)
    commit = load_json(cfg.facts_path).get('meta', {}).get('source_commit', '')
    # English generator lines are compared against the catalogs that built each
    # site. If the configured catalog has already moved on, English stays strict.
    baseline_catalog = _published_catalog(cfg, baseline)
    ledger, report = reuse_published(baseline, site, cfg.root / options['reviews'], options, source_commit=commit,
                                     source_root=cfg.source_root, source_settings=cfg.site,
                                     baseline_catalog=baseline_catalog,
                                     current_catalog=current_catalog if baseline_catalog else None)
    retained.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return dict(enabled=True, **{k: v for k, v in report.items() if k != 'pending'},
                english_catalogs_verified=baseline_catalog is not None,
                review_required=len(report['pending']), pending_sample=report['pending'][:20])


def replay(cfg, baseline: Path, out: Path) -> dict:
    from .export_site import export_site
    from .facts.model import KnowledgeModel
    baseline, out = Path(baseline).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError(f'Replay output already exists: {out}')
    out.mkdir(parents=True)
    preview = copy.deepcopy(cfg)
    translation = translation_need(cfg, out / 'english.json')
    if translation['enabled']:
        preview.raw.setdefault('site', {})['english_catalog'] = str(out / 'english.json')
    # The gate itself is what replay measures; the preview must not enforce it.
    preview.raw.setdefault('visual_audit', {})['enabled'] = False
    site = export_site(preview, out=out / 'site')
    model = KnowledgeModel.load(cfg.facts_path)
    report = dict(
        schema=SCHEMA, baseline=str(baseline),
        baseline_build_id=load_json(baseline / 'site-manifest.json').get('build_id'),
        preview_build_id=load_json(site / 'site-manifest.json').get('build_id'),
        outputs=manifest_delta(load_json(baseline / 'site-manifest.json'), load_json(site / 'site-manifest.json')),
        translation=translation,
        visual_reviews=visual_plan(cfg, baseline, site, out / 'retained-visual-reviews.json',
                                   out / 'english.json' if translation['enabled'] else None),
        contract_audit=contract_plan(cfg, model),
        assessment='Estimated model work for this generator on the published input. Not a review result.',
    )
    report['model_work_required'] = bool(report['translation'].get('model_required')
                                         or report['visual_reviews'].get('review_required')
                                         or report['contract_audit'].get('fresh'))
    (out / 'replay.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def summary(report: dict) -> list[str]:
    outputs, t, v, c = report['outputs'], report['translation'], report['visual_reviews'], report['contract_audit']
    lines = [f"outputs: {len(outputs['changed'])} changed, {len(outputs['added'])} added, {len(outputs['removed'])} removed"]
    if t.get('enabled'):
        lines.append(f"translation: {t['model_required']} need a model, {t['fixed_fill']} filled by fixed rules")
    if v.get('enabled'):
        lines.append(f"visual reviews: {v['review_required']} need review "
                     f"(exact {v['exact']}, position {v['position_only']}, presentation {v['presentation_only']}, "
                     f"source {v['source_revision']})")
    if c.get('enabled'):
        lines.append(f"contract audit: {c['fresh']} of {c['batches']} batches need a model call "
                     f"({c['fresh_input_chars']} input chars)")
    lines.append('model work required' if report['model_work_required'] else 'no model work required')
    return lines
