"""Source preservation; no CLI or project source-file IO."""
from __future__ import annotations

import hashlib

from .validate import extract_citations


def source(model, sid):
    if sid.startswith('@analysis/scenario/') and sid not in model.evidence:
        from .consistency_analysis import evidence
        return evidence(model, sid)
    record = model.evidence.get(sid, {})
    excerpt = record.get('context', record)
    if (record.get('commit') != model.meta.get('source_commit')
            or record.get('status') != 'available'
            or not isinstance(excerpt.get('text'), str)
            or hashlib.sha256(excerpt['text'].encode()).hexdigest() != excerpt.get('sha256')
            or type(excerpt.get('line')) is not int or excerpt['line'] < 1
            or not isinstance(record.get('file'), str)):
        raise ValueError(f'Invalid consistency source: {sid}')
    return dict(file=record['file'], line=excerpt['line'],
                text=excerpt['text'], sha256=excerpt['sha256'])


def citation_refs(model, text):
    """Bind existing paragraph citations to an available full source context."""
    refs = []
    for cite in sorted(extract_citations(text)):
        file, _, number = cite.rpartition(':')
        candidates = []
        for sid, record in model.evidence.items():
            if record.get('file') != file or record.get('status') != 'available':
                continue
            excerpt = record.get('context', record)
            start, body = excerpt.get('line'), excerpt.get('text')
            if (type(start) is int and isinstance(body, str)
                    and start <= int(number) <= start + body.count('\n')):
                candidate = source(model, sid)
                candidates.append((len(candidate['text']), sid))
        if candidates:
            refs.append(min(candidates)[1])
    return list(dict.fromkeys(refs))


def contains_statement(statement, paragraph):
    """Match a complete visible statement, including short statements and code."""
    if not statement:
        return False
    if statement == paragraph:
        return True
    start = paragraph.find(statement)
    while start >= 0:
        end = start + len(statement)
        before = paragraph[:start].rstrip()
        if ((not before or before.endswith(('.', '!', '?')))
                and (end == len(paragraph) or paragraph[end].isspace())):
            return True
        start = paragraph.find(statement, start + 1)
    return False


def canonicalize(claims, sources, shared):
    """Share only byte-identical excerpts at the same immutable source location."""
    canonical, locations, aliases = {}, {}, {}
    # Keep explicitly configured names where two selectors select the same code.
    for sid in dict.fromkeys([*shared, *sources]):
        row = sources[sid]
        key = row['file'], row['line'], row['sha256'], row['text']
        name = locations.setdefault(key, sid)
        aliases[sid] = name
        canonical.setdefault(name, row)
    for claim in claims.values():
        claim['evidence'] = list(dict.fromkeys(aliases[sid] for sid in claim.get('evidence', [])))
    return canonical, list(dict.fromkeys(aliases[sid] for sid in shared)), aliases
