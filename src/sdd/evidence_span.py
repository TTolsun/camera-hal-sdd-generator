"""Anchor selection shared by evidence readers. No imports from sdd, so any
evidence module can use it without an import cycle."""
from __future__ import annotations


def select_span(text: str, source: dict) -> tuple[int, int]:
    """Select a unique passage inside an optional uniquely anchored scope."""
    offset, region = 0, text
    if 'scope' in source:
        scope = source['scope']
        offset, limit = select_span(text, scope)
        region = text[offset:limit]
    start, end = source['start'], source['end']
    if not start or not end or region.count(start) != 1:
        raise ValueError('시작 앵커가 없거나 유일하지 않습니다.')
    begin = region.index(start)
    finish = region.find(end, begin + len(start))
    if finish < 0:
        raise ValueError('종료 앵커가 선택 범위 안에 없습니다.')
    return offset + begin, offset + finish + len(end)
