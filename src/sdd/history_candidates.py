"""Find commit messages that may explain configured source excerpts.

For each available Git source excerpt of a design topic, list the commits
that touched that line range (`git log -L`) and the commits each line came
from across moves and copies (`git blame -w -M -C`). The output is a review
queue: nothing here edits configuration, calls a model or approves evidence.
A candidate is only a place to look for design intent.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .evidence_span import select_span
from .history_evidence import REVISION, trailers

# 변경 의도를 거의 담지 않는 제목. 제외하지 않고 표시만 한다.
_LOW_SIGNAL = re.compile(
    r'\b(typo|whitespace|format(ting)?|clang-format|checkstyle|style|rename|renaming|move|reorder|clean ?up|cosmetic|'
    r'fix (the )?build|build fix|merge|revert|license|spdx|copyright|include|header)\b', re.I)
# diff 줄은 공백·+·-·@@·diff·index·---·+++ 로 시작하므로 이 표식과 겹치지 않는다.
# 제어 문자는 Windows 명령 인자에서 빠질 수 있어 쓰지 않는다.
_MARK = 'SDD-REVISION:'


def _run(root, *args) -> str:
    result = subprocess.run(['git', '-c', 'i18n.logOutputEncoding=UTF-8', *args], cwd=root,
                            capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise ValueError((result.stderr or '').strip() or f"git {args[0]} 실패")
    return result.stdout


def range_history(root, commit: str, file: str, first: int, last: int) -> list[str]:
    """Commits touching the range, newest first, following the range through edits."""
    out = _run(root, 'log', f'-L{first},{last}:{file}', f'--format={_MARK}%H', commit)
    return [line[len(_MARK):].strip() for line in out.splitlines() if line.startswith(_MARK)]


def line_origins(root, commit: str, file: str, first: int, last: int) -> dict[str, dict]:
    """Commits that introduced the current lines, across whitespace, moves and copies."""
    out = _run(root, 'blame', '--porcelain', '-w', '-M', '-C', f'-L{first},{last}', commit, '--', file)
    origins: dict[str, dict] = {}
    current = None
    for line in out.splitlines():
        head = line.split(' ')
        if REVISION.fullmatch(head[0]) and len(head) >= 3:
            current = origins.setdefault(head[0], {'lines': 0, 'files': set()})
            current['lines'] += 1
        elif current is not None and line.startswith('filename '):
            current['files'].add(line[len('filename '):])
    return origins


def describe(root, revision: str) -> dict:
    meta = _run(root, 'show', '-s', '--format=%aI%x00%s%x00%B', revision).rstrip('\n').split('\x00', 2)
    date, subject, body = (meta + ['', '', ''])[:3]
    found = trailers(body)
    lines = [line for line in body.strip().splitlines()[1:] if line.strip()]
    trailer_count = sum(len(v) for v in found.values())
    return {'revision': revision, 'date': date, 'subject': subject, 'message': body.rstrip('\n') + '\n',
            'body_lines': max(0, len(lines) - trailer_count),
            'change_id': (found.get('Change-Id') or [None])[0],
            'links': found.get('Reviewed-on', []) + found.get('Link', [])}


def anchors(message: str) -> dict | None:
    """Anchors for the whole message without trailers, if they select it uniquely."""
    body = message.strip()
    found = trailers(body)
    paragraphs = [p for p in re.split(r'\n\s*\n', body) if p.strip()]
    if found and len(paragraphs) > 1:
        paragraphs = paragraphs[:-1]
    lines = [line.strip() for line in '\n\n'.join(paragraphs).splitlines() if line.strip()]
    # 제목 한 줄뿐이면 시작·종료 앵커를 나눌 수 없고, 설계 의도도 거의 담지 않는다.
    if len(lines) < 2 or body.count(lines[0]) != 1:
        return None
    selected = {'start': lines[0], 'end': lines[-1]}
    try:
        begin, finish = select_span(message, selected)
    except ValueError:
        return None
    # 종료 줄이 본문 중간에도 있으면 발췌가 일찍 끝난다. 마지막 출현까지 선택할 때만 제안한다.
    if finish != message.rfind(lines[-1]) + len(lines[-1]):
        return None
    return selected


def comment_anchors(message: str) -> dict | None:
    """Anchors selecting a whole review comment, including a one-line comment."""
    lines = [line.strip() for line in message.strip().splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) >= 2:
        selected = {'start': lines[0], 'end': lines[-1]}
    else:
        # 리뷰 코멘트는 한 줄이 흔하다. 단어 경계에서 둘로 나눠 시작·종료 앵커를 만든다.
        words = lines[0].split(' ')
        if len(words) < 2:
            return None
        middle = len(words) // 2
        selected = {'start': ' '.join(words[:middle]), 'end': ' '.join(words[middle:])}
    try:
        begin, finish = select_span(message, selected)
    except ValueError:
        return None
    if message[begin:finish].strip() != message.strip():
        return None
    return selected


def reviews(cfg, change_id: str | None, links: list[str], files: set[str], limit: int) -> dict | None:
    """Comments of the change from a local snapshot, or how to fetch a missing one."""
    from . import review_evidence
    if not change_id or not review_evidence.CHANGE_ID.fullmatch(change_id):
        return None
    try:
        snapshot = review_evidence.load(cfg.reviews_dir, change_id)
    except ValueError:
        base = next((link.split('/c/', 1)[0] for link in links if '/c/' in link), '<GERRIT>')
        return {'status': 'missing', 'change_id': change_id, 'base_url': base}
    comments = []
    for comment in snapshot['comments']:
        if not str(comment.get('message', '')).strip():
            continue
        flags = ['Gerrit 자동 알림'] if review_evidence.automated(comment) else []
        if comment.get('unresolved'):
            flags.append('미해결로 닫히지 않은 코멘트')
        comments.append({**comment, 'signals': flags, 'same_file': comment.get('path') in files,
                         'anchors': comment_anchors(comment['message'])})
    # 자동 알림이 아닌 코멘트, 발췌와 같은 파일에 단 코멘트를 먼저 보인다.
    comments.sort(key=lambda c: ('Gerrit 자동 알림' in c['signals'], not c['same_file'], c['date'], c['id']))
    return {'status': 'available', 'change_id': change_id, 'number': snapshot.get('number'),
            'subject': snapshot.get('subject', ''), 'total': len(comments), 'comments': comments[:limit]}


def signals(info: dict) -> list[str]:
    flags = []
    if info['body_lines'] == 0:
        flags.append('제목만 있음')
    if _LOW_SIGNAL.search(info['subject']):
        flags.append('정리성 변경으로 보이는 제목')
    return flags


def collect(cfg, model, sections: list[str] | None = None, limit: int = 8, review_limit: int = 6) -> dict:
    commit = str(model.meta.get('source_commit', ''))
    if not REVISION.fullmatch(commit):
        raise ValueError('facts에 불변 Git 커밋이 없습니다.')
    root = cfg.source_root
    cache: dict[str, dict] = {}
    topics = []
    for sec in cfg.sections():
        if sections and sec['id'] not in sections:
            continue
        for topic in sec.get('design_topics', []):
            entry = {'section': sec['id'], 'topic': topic['id'], 'question': topic.get('question', ''),
                     'existing_commits': [s['revision'] for s in topic.get('sources', [])
                                          if s.get('kind') == 'commit' and isinstance(s.get('revision'), str)],
                     'existing_comments': [[s.get('change'), s.get('comment')] for s in topic.get('sources', [])
                                           if s.get('kind') == 'review'],
                     'excerpts': [], 'skipped': []}
            for source in topic.get('sources', []):
                key = f"{sec['id']}/{topic['id']}/{source['id']}"
                record = model.evidence.get(key, {})
                if source.get('kind') in ('product', 'commit', 'review'):
                    continue
                if record.get('status') != 'available' or record.get('commit') != commit:
                    entry['skipped'].append({'source': source['id'],
                                             'reason': record.get('reason', '현재 커밋의 근거 발췌가 없습니다.')})
                    continue
                file, first, last = record['file'], record['line'], record['end_line']
                try:
                    history = range_history(root, commit, file, first, last)
                    origins = line_origins(root, commit, file, first, last)
                except ValueError as exc:
                    entry['skipped'].append({'source': source['id'], 'reason': str(exc)})
                    continue
                files = {file}.union(*(origin['files'] for origin in origins.values()))
                ordered = list(dict.fromkeys(history + sorted(origins, key=lambda r: -origins[r]['lines'])))
                candidates = []
                for revision in ordered[:limit]:
                    info = cache.get(revision) or cache.setdefault(revision, describe(root, revision))
                    roles = []
                    if history and revision == history[-1]:
                        roles.append('이 파일에서 범위 최초 도입')
                    if history and revision == history[0]:
                        roles.append('범위 최근 변경')
                    if revision in origins:
                        moved = sorted(origins[revision]['files'] - {file})
                        roles.append(f"현재 줄 {origins[revision]['lines']}개의 출처"
                                     + (f" (원래 파일: {', '.join(moved)})" if moved else ''))
                    later = history.index(revision) if revision in history else None
                    candidates.append({
                        'revision': revision, 'date': info['date'], 'subject': info['subject'],
                        'roles': roles, 'signals': signals(info),
                        # 이후 같은 범위를 바꾼 커밋 수. 0보다 크면 메시지의 의도가 현재 코드와 어긋났을 수 있다.
                        'later_changes': later,
                        'change_id': info['change_id'], 'links': info['links'],
                        'already_linked': revision in entry['existing_commits'],
                        'anchors': anchors(info['message']), 'message': info['message'],
                        'reviews': reviews(cfg, info['change_id'], info['links'], files, review_limit),
                    })
                    for comment in (candidates[-1]['reviews'] or {}).get('comments', []):
                        comment['already_linked'] = [info['change_id'], comment['id']] in entry['existing_comments']
                entry['excerpts'].append({'source': source['id'], 'file': file, 'line': first, 'end_line': last,
                                          'history_total': len(history), 'candidates': candidates})
            if entry['excerpts'] or entry['skipped']:
                topics.append(entry)
    return {'schema': 1, 'source_commit': commit, 'limit': limit, 'topics': topics,
            'note': '후보는 설계 의도를 찾을 위치일 뿐이며, 사람이 메시지·코멘트를 읽고 고른 것만 '
                    'kind: commit 또는 kind: review 근거로 등록합니다.'}


def _yaml_snippet(candidate: dict) -> str:
    anchor = candidate['anchors']
    # JSON 문자열은 YAML 문자열이기도 하므로 따옴표·콜론이 섞인 제목도 그대로 붙여 넣을 수 있다.
    return '\n'.join([
        f"- id: why-{candidate['revision'][:8]}",
        '  kind: commit',
        f"  revision: {candidate['revision']}",
        f"  start: {json.dumps(anchor['start'], ensure_ascii=False)}",
        f"  end: {json.dumps(anchor['end'], ensure_ascii=False)}",
    ])


def _review_snippet(change_id: str, comment: dict) -> str:
    anchor = comment['anchors']
    return '\n'.join([
        f"- id: review-{comment['id'][:12]}",
        '  kind: review',
        f"  change: {change_id}",
        f"  comment: {json.dumps(comment['id'], ensure_ascii=False)}",
        f"  start: {json.dumps(anchor['start'], ensure_ascii=False)}",
        f"  end: {json.dumps(anchor['end'], ensure_ascii=False)}",
    ])


def _fence(text: str) -> str:
    return '`' * max(3, 1 + max((len(m[0]) for m in re.finditer(r'`+', text)), default=0))


def _review_lines(review: dict) -> list[str]:
    change = review['change_id']
    if review['status'] == 'missing':
        raw = f"reviews-raw/{change[:9]}"
        return ['리뷰 스냅숏이 없습니다. 논의를 확인하려면 두 응답을 저장한 뒤 가져옵니다. '
                'Change-Id가 여러 브랜치에 있으면 `<project>~<branch>~<Change-Id>` 형식으로 지정합니다.', '',
                '```powershell',
                f'curl.exe -u <사용자> "{review["base_url"]}/a/changes/{change}?o=MESSAGES" -o {raw}-change.json',
                f'curl.exe -u <사용자> "{review["base_url"]}/a/changes/{change}/comments" -o {raw}-comments.json',
                f'uv run sdd --config <CFG> import-reviews --change {raw}-change.json --comments {raw}-comments.json',
                '```', '']
    lines = [f"리뷰 코멘트 (Change {review['number'] or change[:9]}): 전체 {review['total']}개 중 "
             f"{len(review['comments'])}개를 표시합니다.", '']
    for comment in review['comments']:
        # /PATCHSET_LEVEL, /COMMIT_MSG 같은 특수 경로와 줄이 없는 코멘트는 경로만 보인다.
        path, line = comment.get('path'), comment.get('line')
        where = f" `{path}:{line}`" if path and line else (f" `{path}`" if path else '')
        flags = ', '.join(comment['signals']) or '없음'
        lines += [f"- `{comment['id']}` {comment['author']} {comment['date'][:10]}{where}"
                  f" (같은 파일: {'예' if comment['same_file'] else '아니요'}, 주의 신호: {flags})"]
        fence = _fence(comment['message'])
        lines += ['', f'  {fence}text', *['  ' + line for line in comment['message'].rstrip('\n').splitlines()],
                  f'  {fence}', '']
        if comment.get('already_linked'):
            lines += ['  이미 이 설계 주제의 근거로 연결되어 있습니다.', '']
        elif comment['anchors'] and not comment['signals']:
            lines += ['  ```yaml', *['  ' + line for line in _review_snippet(change, comment).splitlines()],
                      '  ```', '']
    return lines


def markdown(report: dict) -> str:
    lines = ['# 설계 근거 후보 (커밋·리뷰 기록)', '',
             f"facts 커밋: `{report['source_commit']}`", '',
             '> ' + report['note'],
             '> 커밋 메시지는 작성 당시의 의도입니다. `이후 변경`이 1 이상이면 현재 코드와 다를 수 있으므로 소스 근거와 함께 대조하세요.',
             '> 리뷰 코멘트는 논의 과정입니다. 제안이 채택됐는지는 답글과 최종 코드로 확인하세요.',
             '']
    if not report['topics']:
        lines.append('후보를 찾을 설계 주제가 없습니다. 설계 주제에 Git 소스 근거를 먼저 연결하세요.')
    for topic in report['topics']:
        lines += [f"## {topic['section']} / {topic['topic']}", '']
        if topic['question']:
            lines += [f"질문: {topic['question']}", '']
        for skipped in topic['skipped']:
            lines.append(f"- 건너뜀 `{skipped['source']}`: {skipped['reason']}")
        if topic['skipped']:
            lines.append('')
        for excerpt in topic['excerpts']:
            lines += [f"### `{excerpt['file']}:{excerpt['line']}-{excerpt['end_line']}` ({excerpt['source']})", '',
                      f"범위를 바꾼 커밋 {excerpt['history_total']}개 중 상위 {len(excerpt['candidates'])}개를 표시합니다.", '']
            if not excerpt['candidates']:
                lines += ['후보가 없습니다.', '']
            for c in excerpt['candidates']:
                flags = ', '.join(c['signals']) or '없음'
                later = '알 수 없음 (범위 이력 밖의 줄 출처)' if c['later_changes'] is None else c['later_changes']
                lines += [f"#### `{c['revision'][:12]}` {c['subject']}", '',
                          f"- 날짜: {c['date'][:10]}",
                          f"- 역할: {'; '.join(c['roles']) or '없음'}",
                          f"- 이후 변경: {later}",
                          f"- 주의 신호: {flags}"]
                if c['change_id']:
                    lines.append(f"- Change-Id: `{c['change_id']}` (리뷰 코멘트에 실제 논의가 있을 수 있습니다)")
                for link in c['links']:
                    lines.append(f"- 리뷰 링크: {link}")
                if c['already_linked']:
                    lines.append('- 이미 이 설계 주제의 근거로 연결되어 있습니다.')
                fence = '`' * max(3, 1 + max((len(m[0]) for m in re.finditer(r'`+', c['message'])), default=0))
                lines += ['', f'{fence}text', c['message'].rstrip('\n'), fence, '']
                if c['anchors'] and not c['already_linked']:
                    lines += ['메시지를 근거로 쓰기로 했다면 이 주제의 `sources`에 추가합니다.', '',
                              '```yaml', _yaml_snippet(c), '```', '']
                if c.get('reviews'):
                    lines += _review_lines(c['reviews'])
    return '\n'.join(lines).rstrip('\n') + '\n'


def write(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    data, text = out_dir / 'history-candidates.json', out_dir / 'history-candidates.md'
    data.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    text.write_text(markdown(report), encoding='utf-8', newline='\n')
    return data, text
