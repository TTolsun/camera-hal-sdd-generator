"""Bind ordinary source-question pages to extracted scenario appendices."""
from __future__ import annotations

import hashlib
import copy
import html
import json
import re

import yaml

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


def _same_encoded_overview(previous, current):
    """Allow Mermaid label encoding changes, never narrative or graph changes."""
    blocks = re.compile(r'```mermaid\n(.*?)\n```', re.S)
    old, new = blocks.split(previous), blocks.split(current)
    if len(old) != 3 or len(new) != 3 or old[::2] != new[::2]:
        return False
    quoted = re.compile(r'"([^"\n]*)"')
    before, after = quoted.split(old[1]), quoted.split(new[1])
    if len(before) != len(after) or before[::2] != after[::2]:
        return False
    def literal(value):
        return re.sub(r'#([0-9]+);', lambda m: chr(int(m[1])), value)
    return all(html.unescape(a) == literal(b) for a, b in zip(before[1::2], after[1::2]))


def refresh_encoded_appendix(cfg, model, section, manuscript, previous):
    """Re-render a proven encoding-only appendix without rewriting LLM prose.

    Previous overview/details are obtained from the previous generator using
    the same facts. Both old native prose and the new manuscript are verified.
    Source, questions, graph relationships and human-review status stay bound.
    """
    from .document_metadata import split_frontmatter
    from .generated_design import verify as verify_design
    from .generated_visuals import from_manuscript
    if previous.get('source_commit') != model.meta['source_commit']:
        raise ValueError('Previous appendix snapshot uses another source commit')
    metadata, body = split_frontmatter(manuscript)
    verify_design(model, section, manuscript, cfg=cfg)
    if 'generated_visuals' in metadata:
        from_manuscript(cfg, model, section, manuscript)
    document, expected = appendix(cfg, model, section)
    if previous.get('metadata') != expected or any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError('Scenario evidence or settings changed; encoding-only refresh is forbidden')
    old_overview, old_details = previous.get('overview'), previous.get('details')
    if old_details != document.details or not isinstance(old_overview, str):
        raise ValueError('Scenario details changed; regenerate instead of retaining prose')
    if document.overview in body and document.details in body:
        return manuscript
    if (body.count(old_overview) != 1 or body.count(old_details) != 1
            or not _same_encoded_overview(old_overview, document.overview)):
        raise ValueError('Previous appendix or Mermaid relationships do not match the current facts')
    updated = body.replace(old_overview, document.overview, 1)
    result = copy.deepcopy(metadata)
    digest = lambda text: hashlib.sha256(text.strip().encode()).hexdigest()
    result['generated_design']['body_sha256'] = digest(updated)
    if 'generated_visuals' in result:
        result['generated_visuals']['body_sha256'] = digest(updated)
    result.setdefault('managed_format_refresh', []).append(dict(
        source_commit=model.meta['source_commit'], previous_body_sha256=digest(body),
        body_sha256=digest(updated), previous_overview_sha256=digest(old_overview),
        overview_sha256=digest(document.overview), change='Mermaid literal encoding only',
        new_inference=False, human_review='unchanged'))
    text = '---\n' + yaml.safe_dump(result, allow_unicode=True, sort_keys=False) + '---\n' + updated
    verify_design(model, section, text, cfg=cfg)
    if 'generated_visuals' in metadata:
        from_manuscript(cfg, model, section, text)
    verify(cfg, model, section, result, updated)
    return text


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
