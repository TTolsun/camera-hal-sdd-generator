"""Generated next-step navigation, separate from source-backed runtime claims."""
from __future__ import annotations

import hashlib
import os
from pathlib import PurePosixPath
import re

from .config import section_output
from .document_metadata import split_frontmatter
from .trial_workspace import contained_path

FOOTER = '다음 단계: [{next_title}]({next_link})'


def section_next(section):
    nxt = section.get('next') or {}
    return str(nxt.get('title', '시스템 개요')), str(nxt.get('link', 'overview.md'))


def ordered_scenarios(cfg, model):
    ids = [row['id'] for row in cfg.scenarios()]
    known = [(sid, model.scenarios[sid]) for sid in ids if sid in model.scenarios]
    return known + sorted((sid, sc) for sid, sc in model.scenarios.items() if sid not in ids)


def _next(cfg, model, name, meta):
    section = next((s for s in cfg.sections() if s['id'] == meta.get('section')), None)
    if section is None:
        return None
    sid = meta.get('scenario_id')
    if section.get('kind') == 'per-scenario' and not section.get('index_only'):
        ordered = ordered_scenarios(cfg, model)
        for index, (key, _) in enumerate(ordered):
            if sid == key and name == f'scenarios/{key}.md':
                if index + 1 < len(ordered):
                    following = ordered[index + 1][1]
                    return following.title, f'scenarios/{following.id}.md'
                return '핵심 시나리오 목록', 'scenarios/index.md'
        return None
    return section_next(section) if name == section_output(section) else None


def _outside_fence(text):
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if not match:
            continue
        marker, suffix = match.groups()
        if fence is None:
            fence = marker
        elif marker[0] == fence[0] and len(marker) >= len(fence) and not suffix.strip():
            fence = None
    return fence is None


def checked_footer(cfg, model, name, meta, body):
    """Recognize only the canonical final link to a current local document.

    Custom hints, mixed prose, fragments and examples stay in the ordinary
    claim collector. A recognized missing/stale target fails before review.
    """
    expected = _next(cfg, model, name, meta)
    if expected is None or not (cfg.templates_dir/'page.md').read_text(encoding='utf-8').strip().endswith(FOOTER):
        return None
    title, target = expected
    if any(c in target for c in ('#', '?', ':', '\\')) or not target.endswith('.md'):
        return None
    path = contained_path(cfg.sdd_dir, target)
    relative = os.path.relpath(path, (cfg.sdd_dir/name).parent).replace('\\', '/')
    footer = FOOTER.format(next_title=title, next_link=relative)
    paragraphs = body.split('\n\n')
    indices = [i for i, p in enumerate(paragraphs) if p.strip()]
    if not indices:
        return None
    index = indices[-1]
    if paragraphs[index].rstrip('\n') != footer or not _outside_fence('\n\n'.join(paragraphs[:index])):
        return None
    if not path.is_file():
        raise ValueError(f'Generated next-step target missing: {name} -> {target}')
    raw = path.read_bytes()
    target_meta, target_body = split_frontmatter(raw.decode('utf-8').replace('\r\n', '\n'))
    if target_meta.get('source_commit') != model.meta.get('source_commit'):
        raise ValueError(f'Generated next-step target source commit mismatch: {target}')
    heading = re.search(r'^# (.+)$', target_body, re.M)
    if heading is None or heading[1] != title:
        return None
    return dict(document=name, paragraph=index, text=paragraphs[index], target=PurePosixPath(target).as_posix(),
                title=title, target_sha256=hashlib.sha256(raw).hexdigest(),
                assessment='generated navigation; current target exists; not a runtime contract verdict')
