"""Shared role-input validation without assembly/render dependencies."""
import re


KINDS = {
    'fact': '관측된 사실 · 정적 소스 설명',
    'hypothesis': '가설 · 검증 전',
    'unmeasured': '미측정 효과',
    'decision_request': '결정 요청 · 승인 아님',
}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Reader paths: {name} must be nonempty')
    return value


def _line(value, name):
    value = _text(value, name)
    if '\n' in value or '\r' in value:
        raise ValueError(f'Reader paths: {name} must be one line')
    return value


def _items(value, name):
    if not isinstance(value, list) or not value:
        raise ValueError(f'Reader paths: {name} must be a nonempty list')
    return value


def _mapping(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise ValueError(f'Reader paths: expected fields {sorted(required)}')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', value):
        raise ValueError('Reader paths: IDs must be lowercase slugs')
    return value
