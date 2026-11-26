"""Commit-message excerpts as design evidence.

A commit message records why a change was made at that time. It is not
evidence of current behavior: later commits may have changed the code.
The selector pins a full commit hash, which must be an ancestor of the
facts commit, and anchors inside the message, never a guessed line range.
No network requests or model calls live here.
"""
from __future__ import annotations

import hashlib
import re
import subprocess

from .evidence_span import select_span

ORIGIN = 'commit-message'
REVISION = re.compile(r'[0-9a-f]{40}')
_TRAILER = re.compile(r'^([A-Za-z][A-Za-z0-9-]*):\s*(\S.*)$')


def citation_file(revision: str) -> str:
    # '@' marks evidence that is not a source path. Publication and tracked-file
    # checks already skip such names; '.txt' keeps the existing citation token.
    return f'@commit/{revision[:12]}.txt'


def _git(root, *args, check=True):
    result = subprocess.run(['git', '-c', 'i18n.logOutputEncoding=UTF-8', *args], cwd=root,
                            capture_output=True, encoding='utf-8', errors='strict')
    if check and result.returncode:
        raise ValueError((result.stderr or '').strip() or f"git {args[0]} 실패")
    return result


def message(root, revision: str) -> str:
    return _git(root, 'show', '-s', '--format=%B', revision).stdout.rstrip('\n') + '\n'


def trailers(text: str) -> dict[str, list[str]]:
    """Parse the last paragraph as Git trailers when every line is one."""
    paragraphs = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    if len(paragraphs) < 2:
        return {}
    lines = [line for line in paragraphs[-1].splitlines() if line.strip()]
    if not lines or not all(_TRAILER.match(line) for line in lines):
        return {}
    found: dict[str, list[str]] = {}
    for line in lines:
        key, value = _TRAILER.match(line).groups()
        found.setdefault(key, []).append(value.strip())
    return found


def record(root, source: dict, commit: str) -> dict:
    """Return an available evidence record or raise ValueError with a reason."""
    revision = source.get('revision', '')
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ValueError('revision에는 40자리 커밋 해시가 필요합니다.')
    ancestry = _git(root, 'merge-base', '--is-ancestor', revision, commit, check=False)
    if ancestry.returncode == 1:
        raise ValueError('근거 커밋이 facts 커밋의 이력에 없습니다.')
    if ancestry.returncode:
        raise ValueError('해당 저장소에서 근거 커밋을 찾을 수 없습니다.')
    try:
        text = message(root, revision)
        meta = _git(root, 'show', '-s', '--format=%aI%x00%s', revision).stdout.rstrip('\n').split('\x00')
    except UnicodeDecodeError:
        raise ValueError('커밋 메시지를 UTF-8로 읽을 수 없습니다.') from None
    begin, finish = select_span(text, source)
    excerpt = text[begin:finish]
    if len(excerpt) > int(source.get('max_chars', 12000)):
        raise ValueError('근거 발췌가 허용 길이를 초과했습니다.')
    line = text[:begin].count('\n') + 1
    change = trailers(text).get('Change-Id', [])
    result = {
        'commit': commit, 'selector': source, 'status': 'available', 'origin': ORIGIN,
        'file': citation_file(revision), 'line': line, 'end_line': line + excerpt.count('\n'),
        'text': excerpt, 'sha256': hashlib.sha256(excerpt.encode()).hexdigest(),
        # 커밋 메시지는 소스 파일이 아니므로 파일 전체 고정 근거로 범위 검사에 쓰지 않는다.
        'whole_file': False,
        'revision': revision, 'revision_date': meta[0], 'subject': meta[1] if len(meta) > 1 else '',
    }
    if change:
        result['change_id'] = change[0]
    if source.get('sha256') and result['sha256'] != source['sha256']:
        result.update(status='needs-review', reason='근거 본문이 변경됐습니다. 연결된 설계 설명을 재검토하세요.')
    return result


def configuration_errors(prefix: str, source: dict) -> list[str]:
    errors = []
    if not isinstance(source.get('revision'), str) or not REVISION.fullmatch(source['revision']):
        errors.append(f'{prefix}: kind: commit에는 40자리 revision 해시가 필요합니다.')
    for field in ('start', 'end'):
        if not isinstance(source.get(field), str) or not source[field].strip():
            errors.append(f'{prefix}: {field}는 비어 있지 않은 문자열이어야 합니다.')
    for field in ('file', 'scope', 'whole_file', 'impact'):
        if field in source:
            errors.append(f'{prefix}: kind: commit에는 {field}를 쓸 수 없습니다.')
    return errors
