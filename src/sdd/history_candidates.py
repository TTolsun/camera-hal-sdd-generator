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


def signals(info: dict) -> list[str]:
    flags = []
    if info['body_lines'] == 0:
        flags.append('제목만 있음')
    if _LOW_SIGNAL.search(info['subject']):
        flags.append('정리성 변경으로 보이는 제목')
    return flags


def collect(cfg, model, sections: list[str] | None = None, limit: int = 8) -> dict:
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
                     'excerpts': [], 'skipped': []}
            for source in topic.get('sources', []):
                key = f"{sec['id']}/{topic['id']}/{source['id']}"
                record = model.evidence.get(key, {})
                if source.get('kind') in ('product', 'commit'):
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
                    })
                entry['excerpts'].append({'source': source['id'], 'file': file, 'line': first, 'end_line': last,
                                          'history_total': len(history), 'candidates': candidates})
            if entry['excerpts'] or entry['skipped']:
                topics.append(entry)
    return {'schema': 1, 'source_commit': commit, 'limit': limit, 'topics': topics,
            'note': '후보는 설계 의도를 찾을 위치일 뿐이며, 사람이 메시지를 읽고 고른 것만 kind: commit 근거로 등록합니다.'}


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


def markdown(report: dict) -> str:
    lines = ['# 설계 근거 후보 (커밋 기록)', '',
             f"facts 커밋: `{report['source_commit']}`", '',
             '> ' + report['note'],
             '> 커밋 메시지는 작성 당시의 의도입니다. `이후 변경`이 1 이상이면 현재 코드와 다를 수 있으므로 소스 근거와 함께 대조하세요.',
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
    return '\n'.join(lines).rstrip('\n') + '\n'


def write(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    data, text = out_dir / 'history-candidates.json', out_dir / 'history-candidates.md'
    data.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    text.write_text(markdown(report), encoding='utf-8', newline='\n')
    return data, text
