"""Stable links to rendered index rows, without changing extracted manuscripts."""
from __future__ import annotations

import hashlib
import html
import re


def _text(value: str) -> str:
    return html.unescape(re.sub(r'<[^>]*>', '', value)).strip()


def index_navigation(document: str, page: str, title: str) -> tuple[str, list[dict]]:
    """Only generated class/function tables become searchable symbol entries."""
    entries = []
    seen = {}
    package = ''
    parts = re.split(r'(<h2\b[^>]*>.*?</h2>|<table>.*?</table>)', document, flags=re.S)
    for index, part in enumerate(parts):
        if part.startswith('<h2'):
            package = _text(part)
            continue
        if not part.startswith('<table>'):
            continue
        headers = re.findall(r'<th\b[^>]*>(.*?)</th>', part, re.S)
        if not headers or _text(headers[0]) not in ('클래스', '함수'):
            continue
        kind = 'class' if _text(headers[0]) == '클래스' else 'function'

        def row(match):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', match[1], re.S)
            if len(cells) < 2:
                return match[0]
            name, location = _text(cells[0]), _text(cells[1])
            location = re.sub(r':\d+(?:-\d+)?(?=\s|$)', '', location)
            key = '\0'.join((package, name, location))
            seen[key] = seen.get(key, 0) + 1
            suffix = '' if seen[key] == 1 else f'-{seen[key]}'
            anchor = 'symbol-' + hashlib.sha256(key.encode()).hexdigest()[:16] + suffix
            entries.append(dict(title=name, page=title, url=page + '#' + anchor, kind='symbol'))
            return (f'<tr id="{anchor}" tabindex="-1" data-symbol-kind="{kind}">'
                    + match[1] + '</tr>')

        parts[index] = re.sub(r'<tr>(.*?)</tr>', row, part, flags=re.S)
    return ''.join(parts), entries
