"""Compact generated reading aids while preserving their unique information."""
from __future__ import annotations

import html
import posixpath
import re
from urllib.parse import quote


def cells(row: str, tag: str = 'td') -> tuple[str, ...]:
    return tuple(cell.strip() for cell in re.findall(rf'<{tag}\b[^>]*>(.*?)</{tag}>', row, re.S))


def reference_cells(row: str) -> tuple[str, ...]:
    return tuple(re.findall(r'<td\b[^>]*>.*?</td>', row, re.S))


def simple_table(table: str, *, labeled: bool = False) -> bool:
    """Reject captions, extra text/sections and custom structural attributes."""
    parts = re.fullmatch(r'<table>\s*<thead>\s*<tr>(.*?)</tr>\s*</thead>\s*<tbody>(.*?)</tbody>\s*</table>', table, re.S)
    if not parts or table.count('<table>') != 1:
        return False
    head, body = parts.groups()
    if not re.findall(r'<th>.*?</th>', head, re.S) or re.sub(r'<th>.*?</th>', '', head, flags=re.S).strip():
        return False
    rows = re.findall(r'<tr>(.*?)</tr>', body, re.S)
    if not rows or re.sub(r'<tr>.*?</tr>', '', body, flags=re.S).strip():
        return False
    cell = r'<td(?: data-label="[^"]*")?>.*?</td>' if labeled else r'<td>.*?</td>'
    return all(re.findall(cell, row, re.S) and not re.sub(cell, '', row, flags=re.S).strip() for row in rows)


def compact_tables(document: str) -> str:
    """Only recognized coverage blocks and one-row call tables change form."""
    intro = '질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.'
    common = '코드 근거와 설명 연결'

    def coverage(match):
        prefix, table, suffix = match.groups()
        if not simple_table(table):
            return match[0]
        if cells(table, 'th') != ('설계 질문', '설명 위치', '확인 범위'):
            return match[0]
        items = []
        for row in re.findall(r'<tr>(.*?)</tr>', table, re.S):
            values = cells(row)
            if not values:
                continue
            if len(values) != 3 or values[2] not in (common, common + ' · 실행 확인 항목 별도'):
                return match[0]
            question, links, scope = values
            qualifier = '<p>실행 확인 항목 별도</p>' if scope != common else ''
            items.append('<li><p>' + question + '</p><p>' + links + '</p>' + qualifier + '</li>')
        if not items or re.search(r'\bid=', table):
            return match[0]
        return (prefix + '<ul class="coverage-links">' + ''.join(items) + '</ul>'
                + '<p><span>확인 범위</span>: <span>' + common + '</span></p>' + suffix)

    # Full generated context keeps unrelated/custom tables untouched.
    coverage_pattern = (r'(<details class="note">\s*<summary>설계 질문과 검증 범위</summary>\s*<p>'
                        + re.escape(intro) + r'</p>\s*)(<table>.*?</table>)(\s*</details>)')
    headers = {('확인할 내용', '호출 측과 대상', '구분', '근거'),
               ('호출 지점', '후보 또는 예약 대상', '확인할 경계', '근거')}
    converted = set()

    def single_call(match):
        table = match[0]
        if not simple_table(table):
            return table
        labels = cells(table, 'th')
        rows = [cells(row) for row in re.findall(r'<tr>(.*?)</tr>', table, re.S)]
        rows = [row for row in rows if row]
        if labels not in headers or len(rows) != 1 or len(rows[0]) != len(labels) or re.search(r'\bid=', table):
            return table
        converted.add(labels[0])
        return '<dl class="call-checkpoint">' + ''.join('<dt>' + key + '</dt><dd>' + value + '</dd>'
                                                       for key, value in zip(labels, rows[0])) + '</dl>'

    chunks = re.split(r'(<pre\b[^>]*>.*?</pre>)', document, flags=re.S)
    chunks = [chunk if i % 2 else re.sub(r'<table>.*?</table>', single_call,
                                        re.sub(coverage_pattern, coverage, chunk, flags=re.S), flags=re.S)
              for i, chunk in enumerate(chunks)]
    for i in range(0, len(chunks), 2):
        if '확인할 내용' in converted:
            chunks[i] = chunks[i].replace('주요 확인 지점 1개를 아래 표와 관계도에 표시합니다.',
                                          '주요 확인 지점 1개를 아래 목록과 관계도에 표시합니다.')
        if '호출 지점' in converted:
            chunks[i] = chunks[i].replace('추적 범위와 경계 표에서 후보를 구분한 뒤',
                                          '추적 범위와 경계 항목에서 후보를 구분한 뒤')
    return ''.join(chunks)


def class_targets(indexes: dict[str, str]) -> dict[tuple[str, ...], str]:
    """Only an unambiguous, byte-equal index row can replace a local reference."""
    targets = {}
    for page, document in indexes.items():
        for anchor, row in re.findall(r'<tr id="(symbol-[0-9a-f]{16}(?:-\d+)?)" tabindex="-1" data-symbol-kind="class">(.*?)</tr>', document, re.S):
            key = reference_cells(row)
            targets.setdefault(key, []).append(page + '#' + anchor)
    return {key: values[0] for key, values in targets.items() if len(values) == 1}


def link_related_classes(document: str, page: str, targets: dict[tuple[str, ...], str]) -> str:
    def related(match):
        heading, table = match.groups()
        if cells(table, 'th') != ('클래스', '선언 위치', '상속', '책임 (주석)') or re.search(r'\bid=', table):
            return match[0]
        if not simple_table(table, labeled=True):
            return match[0]
        if any(not re.fullmatch(r'<td(?: data-label="[^"]*")?>', tag) for tag in re.findall(r'<td\b[^>]*>', table)):
            return match[0]
        rows = [reference_cells(row) for row in re.findall(r'<tr>(.*?)</tr>', table, re.S)]
        rows = [row for row in rows if row]
        if not rows or any(row not in targets for row in rows):
            return match[0]
        links = []
        for row in rows:
            label = cells(row[0])[0]
            if re.search(r'<a\b', label):
                return match[0]
            path, anchor = targets[row].split('#', 1)
            target = quote(posixpath.relpath(path, posixpath.dirname(page) or '.'), safe='/.-') + '#' + anchor
            links.append('<li><a href="' + html.escape(target, quote=True) + '">' + label + '</a></li>')
        return (heading + '<p>선언·상속·주석은 각 클래스 링크에서 확인하세요.</p>'
                + '<ul class="related-symbols">' + ''.join(links) + '</ul>')

    return re.sub(r'(<h2 id="관련-클래스">관련 클래스</h2>\s*)<div class="table-scroll stack" tabindex="0" role="region" aria-label="표">(<table>.*?</table>)</div>',
                  related, document, flags=re.S)


def merge_next_step(document: str, following: str) -> tuple[str, str]:
    """Merge the exact generated tail only; retain different destinations/hints."""
    tail = re.search(r'<p>다음 단계: <a href="([^"]+)">([^<>]+)</a></p>\s*$', document)
    control = re.fullmatch(r'(<a class="next" href="([^"]+)">)<small>다음</small>([^<>]+) →</a>', following)
    if not tail or not control or html.unescape(tail[1]) != html.unescape(control[2]):
        return document, following
    if tail[2] != control[3]:
        following = (control[1] + '<small><span>다음</span> · <span>' + control[3] + '</span></small>'
                     + '<span>' + tail[2] + '</span> →</a>')
    return document[:tail.start()], following
