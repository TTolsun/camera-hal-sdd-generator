"""Bind ordinary source-question pages to extracted scenario appendices."""
from __future__ import annotations

from .scenario_document import build, fingerprint


def appendix(cfg, model, section):
    sid = section['scenario']
    settings = next(s for s in cfg.scenarios() if s['id'] == sid)
    sc = model.scenarios.get(sid) if model is not None else None
    if sc is None or not sc.messages or any(m.loc is None for m in sc.messages):
        raise ValueError(f'{sid}: scenario calls or source locations are missing.')
    doc = build(sc, settings, int(cfg.diagram_policy(section).get('max_nodes', 16)))
    metadata = dict(scenario_id=sid, entry=sc.entry, scenario_fingerprint=fingerprint(sc, settings))
    return doc, metadata


def verify(cfg, model, section, metadata, body):
    """The generated prose validator binds prose; also bind every trace record."""
    doc, expected = appendix(cfg, model, section)
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError('Scenario evidence changed; regenerate the source-question page.')
    if doc.overview not in body or doc.details not in body:
        raise ValueError('Scenario appendix differs from the complete extracted call record.')
