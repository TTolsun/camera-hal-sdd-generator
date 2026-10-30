"""Compact evidence navigation without changing manuscripts or review verdicts.

Only known, trailing citation runs and generated excerpt indexes are folded.
The renderer owns HTML presentation; extraction and contract validation stay upstream.
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict

# These shapes are emitted by Markdown and export_site's validated citation linker.
_CODE = r"<code>[^<>]+:\d+</code>"
_ITEM = rf'(?:<a class="citation" href="[^"]+">{_CODE}</a>|{_CODE})'
_SUFFIX = re.compile(rf'(?P<space>\s+)(?P<refs>{_ITEM}(?:,\s*{_ITEM})*)$')
_ITEMS = re.compile(_ITEM)
_LOCAL = re.compile(r'<a href="(#source-[0-9a-f]{16})">([^<>]+:\d+)</a>')


def fold_source_details(document: str) -> str:
    """Collapse the generated excerpt collection, preserving each inner inspector."""
    def section(match):
        heading, body = match.groups()
        count = len(re.findall(r'<a id="source-[0-9a-f]{16}"></a>', body))
        return (heading + '\n<details class="source-excerpts"><summary>소스 발췌 '
                + f'<span>{count}</span>개</summary>\n' + body + '\n</details>\n')

    # SourceDetails emits an introduction followed by anchor/inspector pairs.
    # Stop at the last pair so trailing review metadata stays outside the fold.
    intro = re.escape('<p>같은 발췌는 한 번만 싣습니다. 필요한 원문을 펼쳐 설명과 대조하세요.</p>')
    inspector = r'<p><a id="source-[0-9a-f]{16}"></a></p>\s*<details class="note">.*?</details>'
    return re.sub(r'(<h2 id="소스-근거">소스 근거</h2>)\s*('
                  + intro + r'(?:\s*' + inspector + r')+)\s*', section, document, flags=re.S)


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
    name = '절 전체 근거'
    return (f'<details class="evidence-links evidence-{scope}"><summary>{name} '
            f'<span>{len({cite for cite, _ in refs})}</span>개</summary><ul>{rows}</ul></details>')


def compact_evidence(document: str, valid: set[str]) -> str:
    """Leave unknown/mixed citations, ordinary links and inline code untouched."""
    if not valid:
        return document
    # Local excerpts also work in private/offline sites without a source host.
    destinations = defaultdict(set)
    for match in _LOCAL.finditer(document):
        destinations[html.unescape(match[2])].add(match[1])

    refs_in_section = []

    def paragraph(match):
        body = match[1]
        if body.startswith('근거 원문: '):
            index = body[len('근거 원문: '):]
            links = list(_LOCAL.finditer(index))
            if links and _LOCAL.sub('', index).replace(' · ', '').strip() == '':
                refs = [(html.unescape(m[2]), m[0]) for m in links]
                if all(cite in valid for cite, _ in refs):
                    refs_in_section.extend(refs)
                    return ''
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
        refs_in_section.extend(refs)
        # A non-interactive audit attribute retains the exact paragraph-to-link
        # mapping. It adds no focus target, accessible announcement or search text.
        mapping = html.escape(json.dumps(refs, ensure_ascii=False), quote=True)
        bindings = {cite: sorted(destinations[cite]) for cite, _ in refs if destinations[cite]}
        excerpts = (' data-sdd-excerpts="' + html.escape(json.dumps(bindings), quote=True) + '"'
                    if bindings else '')
        return '<p data-sdd-evidence="' + mapping + '"' + excerpts + '>' + body[:suffix.start()] + '</p>'

    # Never interpret example HTML inside code blocks as document navigation.
    def section(body):
        refs_in_section.clear()
        chunks = re.split(r'(<pre\b[^>]*>.*?</pre>)', body, flags=re.S)
        rendered = ''.join(chunk if i % 2 else re.sub(r'<p>(.*?)</p>', paragraph, chunk, flags=re.S)
                           for i, chunk in enumerate(chunks))
        # Preserve every distinct pinned host and local destination, including
        # citations absent from the generated excerpt index. Never choose an
        # arbitrary excerpt when multiple local versions exist.
        refs = list(dict.fromkeys(refs_in_section))
        hosted = {cite for cite, element in refs if 'class="citation"' in element}
        refs = [(cite, element) for cite, element in refs
                if not (cite in hosted and len(destinations[cite]) == 1 and _LOCAL.fullmatch(element))]
        # The generated index and an offline paragraph can spell the same
        # destination with/without <code>. Keep a single visible link.
        seen = set()
        unique = []
        for cite, element in refs:
            href = re.search(r'href="([^"]+)"', element)
            key = (cite, href[1] if href else element)
            if key not in seen:
                seen.add(key)
                unique.append((cite, element))
        refs = unique
        return rendered + (_panel(refs, 'section', destinations) if refs else '')

    # Headings inside examples must not become section boundaries.
    chunks = re.split(r'(<pre\b[^>]*>.*?</pre>)', document, flags=re.S)
    protected = []
    for i in range(1, len(chunks), 2):
        protected.append(chunks[i])
        chunks[i] = f'\x00SDD_PRE_{len(protected) - 1}\x00'
    # Generated topics are H2 sections. H3–H6 remain inside their parent, so
    # a first paragraph is not followed by a replacement evidence row just
    # because a diagram/subheading comes next. Unsectioned prose is one group.
    parts = re.split(r'(<h[12]\b[^>]*>.*?</h[12]>)', ''.join(chunks), flags=re.S)
    result = ''.join(part if i % 2 else section(part) for i, part in enumerate(parts))
    for i, block in enumerate(protected):
        result = result.replace(f'\x00SDD_PRE_{i}\x00', block)
    return result
