"""Compact evidence navigation without changing manuscripts or review verdicts.

Only known, trailing citation runs and generated excerpt indexes are folded.
The renderer owns HTML presentation; extraction and contract validation stay upstream.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict

# These shapes are emitted by Markdown and export_site's validated citation linker.
_CODE = r"<code>[^<>]+:\d+</code>"
_ITEM = rf'(?:<a class="citation" href="[^"]+">{_CODE}</a>|{_CODE})'
_SUFFIX = re.compile(rf'(?P<space>\s+)(?P<refs>{_ITEM}(?:,\s*{_ITEM})*)$')
_ITEMS = re.compile(_ITEM)
_LOCAL = re.compile(r'<a href="(#source-[0-9a-f]{16})">([^<>]+:\d+)</a>')


def _panel(refs: list[tuple[str, str]], scope: str, destinations=None) -> str:
    groups = defaultdict(list)
    for cite, element in refs:
        file, line = cite.rsplit(':', 1)
        label = f'<code>L{line}</code>'
        if element.startswith('<a '):
            # Retain destinations; the full identity remains available to assistive
            # technology and hover, while the file is printed once per group.
            element = re.sub(r'<a ', lambda _: '<a aria-label="' + html.escape(cite, quote=True) + '" ', element, count=1)
            element = re.sub(r'>.*</a>$', '>' + label + '</a>', element, flags=re.S)
        else:
            element = '<span title="' + html.escape(cite, quote=True) + '">' + label + '</span>'
        local = (destinations or {}).get(cite, set())
        if len(local) == 1 and 'class="citation"' in element:
            # Keep the pinned host link, but make the in-document excerpt the
            # first action. Do not choose between ambiguous excerpts.
            element = element.replace(label, '전체 소스 ' + label)
            element = ('<a href="' + next(iter(local)) + '" aria-label="'
                       + html.escape(cite, quote=True) + ' 발췌">' + label
                       + ' 발췌</a> · ' + element)
        groups[file].append(element)
    rows = ''.join('<li><code>' + html.escape(file) + '</code><span class="evidence-lines">'
                   + ' · '.join(items) + '</span></li>' for file, items in groups.items())
    name = '문단 근거' if scope == 'paragraph' else '절 전체 근거'
    return (f'<details class="evidence-links evidence-{scope}"><summary>{name} '
            f'<span>{len(refs)}</span>개</summary><ul>{rows}</ul></details>')


def compact_evidence(document: str, valid: set[str]) -> str:
    """Leave unknown/mixed citations, ordinary links and inline code untouched."""
    if not valid:
        return document
    # Local excerpts also work in private/offline sites without a source host.
    destinations = defaultdict(set)
    for match in _LOCAL.finditer(document):
        destinations[html.unescape(match[2])].add(match[1])

    def paragraph(match):
        body = match[1]
        if body.startswith('근거 원문: '):
            index = body[len('근거 원문: '):]
            links = list(_LOCAL.finditer(index))
            if links and _LOCAL.sub('', index).replace(' · ', '').strip() == '':
                refs = [(html.unescape(m[2]), m[0]) for m in links]
                if all(cite in valid for cite, _ in refs):
                    return _panel(refs, 'section')
            return match[0]
        # Citation-only paragraphs have no claim to attach a disclosure to.
        # In particular, do not mistake the first citation for prose and fold
        # only the rest of a comma-separated reference list.
        if not _ITEMS.sub('', body).strip(' ,\n\t'):
            return match[0]
        suffix = _SUFFIX.search(body)
        if not suffix or not body[:suffix.start()].strip():
            return match[0]
        refs = []
        for item in _ITEMS.findall(suffix['refs']):
            cite = html.unescape(re.search(r'<code>(.*?)</code>', item)[1])
            if cite not in valid:
                return match[0]
            local = destinations.get(cite, set())
            if not item.startswith('<a ') and len(local) == 1:
                item = f'<a href="{next(iter(local))}">{item}</a>'
            refs.append((cite, item))
        return '<p>' + body[:suffix.start()] + '</p>' + _panel(refs, 'paragraph', destinations)

    # Never interpret example HTML inside code blocks as document navigation.
    chunks = re.split(r'(<pre\b[^>]*>.*?</pre>)', document, flags=re.S)
    return ''.join(chunk if i % 2 else re.sub(r'<p>(.*?)</p>', paragraph, chunk, flags=re.S)
                   for i, chunk in enumerate(chunks))
