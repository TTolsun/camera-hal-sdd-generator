"""Bind ordinary source-question pages to extracted scenario appendices."""
from __future__ import annotations

import hashlib
import json

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


def index_fingerprint(cfg, model, section):
    owners = {s['scenario']: s for s in cfg.sections() if s.get('scenario')}
    ids = [s['id'] for s in cfg.scenarios()]
    if model is None or set(model.scenarios) != set(ids):
        raise ValueError('Scenario index requires exactly the configured extracted scenarios.')
    rows = [dict(id=sid, title=model.scenarios[sid].title, entry=model.scenarios[sid].entry,
                 lead=owners[sid].get('lead', '')) for sid in ids]
    return hashlib.sha256(json.dumps(dict(section=section, rows=rows), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verify_index(cfg, model, section, metadata, body):
    if metadata.get('scenario_index_fingerprint') != index_fingerprint(cfg, model, section):
        raise ValueError('Scenario index inputs changed; regenerate the index.')
    if metadata.get('scenario_index_body_sha256') != hashlib.sha256(body.encode()).hexdigest():
        raise ValueError('Scenario index manuscript changed; regenerate the index.')
