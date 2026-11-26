"""Gerrit review comments as design evidence.

Review discussion often holds the reason a design was chosen or an
alternative was rejected. This module never talks to Gerrit: a person
saves the REST responses and `sdd import-reviews` normalizes them into a
local snapshot. Evidence then pins an anchored passage of one comment.

A review comment records the discussion at that time. It is not evidence
of current behavior, and a snapshot is in-house material: keep it out of
public repositories.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .evidence_span import select_span
from .history_evidence import trailers

ORIGIN = 'review-comment'
CHANGE_ID = re.compile(r'I[0-9a-f]{40}')
_SAFE = re.compile(r'[^A-Za-z0-9_-]')
# Gerrit이 만드는 투표·업로드·빌드 알림. 설계 논의가 아니므로 후보에서 표시만 한다.
_AUTOMATED = re.compile(
    r'^(Uploaded patch set \d+|Patch Set \d+:(\s+[\w-]+[+-]\d+)*\s*(\(\d+ comments?\)\s*)?$|Change has been successfully|'
    r'Build (Started|Successful|Failed)|Removed (the following )?(votes|reviewer)|Removed [\w-]+[+-]\d+ by )', re.I)


def _strip_xssi(raw: bytes) -> object:
    text = raw.decode('utf-8')
    # Gerrit REST 응답은 JSON 앞에 XSSI 방지 접두어를 붙인다.
    if text.startswith(")]}'"):
        text = text.split('\n', 1)[1] if '\n' in text else ''
    return json.loads(text)


def _author(info) -> str:
    if not isinstance(info, dict):
        return ''
    # 이메일은 문서 근거에 필요하지 않으므로 저장하지 않는다.
    for key in ('name', 'username', 'display_name'):
        if isinstance(info.get(key), str) and info[key].strip():
            return info[key].strip()
    return f"account {info['_account_id']}" if '_account_id' in info else ''


def normalize(change_raw: bytes, comments_raw: bytes | None) -> dict:
    """Build a snapshot from a ChangeInfo (with MESSAGES) and a comments map."""
    change = _strip_xssi(change_raw)
    if not isinstance(change, dict) or not CHANGE_ID.fullmatch(str(change.get('change_id', ''))):
        raise ValueError('변경 응답에 Change-Id가 없습니다. /changes/<id>?o=MESSAGES 응답을 지정하세요.')
    if 'messages' not in change:
        raise ValueError('변경 응답에 messages가 없습니다. 요청에 ?o=MESSAGES를 붙이세요.')
    items = []
    for message in change.get('messages') or []:
        items.append({
            'id': str(message['id']), 'type': 'message', 'author': _author(message.get('author')),
            'date': str(message.get('date', '')), 'message': str(message.get('message', '')),
            'path': None, 'line': None, 'patch_set': message.get('_revision_number'),
            'in_reply_to': None, 'unresolved': None, 'tag': message.get('tag'),
        })
    if comments_raw is not None:
        comments = _strip_xssi(comments_raw)
        if not isinstance(comments, dict) or any(not isinstance(v, list) for v in comments.values()):
            raise ValueError('코멘트 응답은 파일 경로별 코멘트 목록이어야 합니다 (/changes/<id>/comments).')
        for path, values in comments.items():
            for comment in values:
                items.append({
                    'id': str(comment['id']), 'type': 'inline', 'author': _author(comment.get('author')),
                    'date': str(comment.get('updated', '')), 'message': str(comment.get('message', '')),
                    'path': path, 'line': comment.get('line'), 'patch_set': comment.get('patch_set'),
                    'in_reply_to': comment.get('in_reply_to'), 'unresolved': comment.get('unresolved'),
                    'tag': comment.get('tag'),
                })
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError('같은 코멘트 id가 여러 번 나옵니다.')
    items.sort(key=lambda item: (item['date'], item['id']))
    return {
        'schema': 1, 'change_id': change['change_id'], 'number': change.get('_number'),
        'project': change.get('project', ''), 'branch': change.get('branch', ''),
        'subject': change.get('subject', ''),
        'inputs': {'change': hashlib.sha256(change_raw).hexdigest(),
                   'comments': hashlib.sha256(comments_raw).hexdigest() if comments_raw is not None else None},
        'comments': items,
    }


def snapshot_path(reviews_dir: Path, change_id: str) -> Path:
    if not CHANGE_ID.fullmatch(change_id):
        raise ValueError('change에는 I로 시작하는 41자리 Change-Id가 필요합니다.')
    return Path(reviews_dir) / f'{change_id}.json'


def write(reviews_dir: Path, snapshot: dict) -> tuple[Path, dict]:
    """Write the snapshot and report which existing comments changed or disappeared."""
    path = snapshot_path(reviews_dir, snapshot['change_id'])
    report = {'added': 0, 'changed': [], 'removed': []}
    if path.exists():
        before = {c['id']: c for c in load(reviews_dir, snapshot['change_id'])['comments']}
        after = {c['id']: c for c in snapshot['comments']}
        report['added'] = len(after.keys() - before.keys())
        report['changed'] = sorted(k for k in after.keys() & before.keys() if after[k] != before[k])
        report['removed'] = sorted(before.keys() - after.keys())
    else:
        report['added'] = len(snapshot['comments'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    return path, report


def load(reviews_dir: Path, change_id: str) -> dict:
    path = snapshot_path(reviews_dir, change_id)
    if not path.is_file():
        raise ValueError(f'리뷰 스냅숏이 없습니다: {path.name}. sdd import-reviews로 가져오세요.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema') != 1 or data.get('change_id') != change_id
            or not isinstance(data.get('comments'), list)):
        raise ValueError(f'리뷰 스냅숏 형식이 올바르지 않습니다: {path.name}')
    return data


def merged_revision(root, change_id: str, commit: str, cache: dict | None = None) -> str | None:
    """The newest ancestor of the facts commit whose trailer names this Change-Id."""
    cache = {} if cache is None else cache
    if (change_id, commit) in cache:
        return cache[(change_id, commit)]
    result = subprocess.run(['git', '-c', 'i18n.logOutputEncoding=UTF-8', 'log', '--format=%H%x00%B%x00',
                             '--fixed-strings', f'--grep=Change-Id: {change_id}', commit],
                            cwd=root, capture_output=True, encoding='utf-8', errors='replace')
    found = None
    if result.returncode == 0:
        parts = result.stdout.split('\x00')
        for revision, body in zip(parts[0::2], parts[1::2]):
            # 본문에서 다른 변경을 언급한 경우가 아니라 trailer로 선언한 커밋만 인정한다.
            if change_id in trailers(body).get('Change-Id', []):
                found = revision.strip()
                break
    cache[(change_id, commit)] = found
    return found


def citation_file(change_id: str, comment_id: str) -> str:
    return f'@review/{change_id[:9]}/{_SAFE.sub("_", comment_id)}.txt'


def automated(comment: dict) -> bool:
    tag = comment.get('tag') or ''
    return tag.startswith('autogenerated:') or bool(_AUTOMATED.match(comment.get('message', '').strip()))


def record(reviews_dir: Path, root, source: dict, commit: str, cache: dict | None = None) -> dict:
    """Return an available evidence record or raise ValueError with a reason."""
    change_id = source.get('change', '')
    if not isinstance(change_id, str) or not CHANGE_ID.fullmatch(change_id):
        raise ValueError('change에는 I로 시작하는 41자리 Change-Id가 필요합니다.')
    snapshot = load(reviews_dir, change_id)
    comment = next((c for c in snapshot['comments'] if c.get('id') == source.get('comment')), None)
    if comment is None:
        raise ValueError('리뷰 스냅숏에 해당 코멘트 id가 없습니다.')
    merged = merged_revision(root, change_id, commit, cache)
    if merged is None:
        raise ValueError('facts 커밋의 이력에 이 Change-Id로 병합된 커밋이 없습니다.')
    text = str(comment['message']).rstrip('\n') + '\n'
    begin, finish = select_span(text, source)
    excerpt = text[begin:finish]
    if len(excerpt) > int(source.get('max_chars', 12000)):
        raise ValueError('근거 발췌가 허용 길이를 초과했습니다.')
    line = text[:begin].count('\n') + 1
    result = {
        'commit': commit, 'selector': source, 'status': 'available', 'origin': ORIGIN,
        'file': citation_file(change_id, comment['id']), 'line': line, 'end_line': line + excerpt.count('\n'),
        'text': excerpt, 'sha256': hashlib.sha256(excerpt.encode()).hexdigest(), 'whole_file': False,
        'change_id': change_id, 'change_number': snapshot.get('number'), 'project': snapshot.get('project', ''),
        'comment_id': comment['id'], 'comment_type': comment.get('type'), 'author': comment.get('author', ''),
        'review_date': comment.get('date', ''), 'reviewed_path': comment.get('path'),
        'reviewed_line': comment.get('line'), 'patch_set': comment.get('patch_set'),
        'merged_revision': merged,
    }
    if source.get('sha256') and result['sha256'] != source['sha256']:
        result.update(status='needs-review', reason='근거 본문이 변경됐습니다. 연결된 설계 설명을 재검토하세요.')
    return result


def configuration_errors(prefix: str, source: dict) -> list[str]:
    errors = []
    if not isinstance(source.get('change'), str) or not CHANGE_ID.fullmatch(source['change']):
        errors.append(f'{prefix}: kind: review에는 I로 시작하는 41자리 change가 필요합니다.')
    if not isinstance(source.get('comment'), str) or not source['comment'].strip():
        errors.append(f'{prefix}: kind: review에는 comment id가 필요합니다.')
    for field in ('start', 'end'):
        if not isinstance(source.get(field), str) or not source[field].strip():
            errors.append(f'{prefix}: {field}는 비어 있지 않은 문자열이어야 합니다.')
    for field in ('file', 'scope', 'whole_file', 'impact', 'revision'):
        if field in source:
            errors.append(f'{prefix}: kind: review에는 {field}를 쓸 수 없습니다.')
    return errors
