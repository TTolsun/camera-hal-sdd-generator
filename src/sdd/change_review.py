"""Build review context from trusted, pinned source windows."""
import json
from difflib import SequenceMatcher


def _index(files):
    indexed = {}
    for file in files:
        path, blob = file['path'], file['git_blob']
        if not path or not blob or path in indexed:
            raise ValueError('Missing source identity or duplicate source path')
        windows = {}
        for window in file['windows']:
            name, start, end, text = (window[k] for k in ('name', 'start_line', 'end_line', 'text'))
            if not name or name in windows or not 1 <= start <= end or not isinstance(text, str):
                raise ValueError(f'Invalid or duplicate evidence window in {path}')
            windows[name] = (start, end, text)
        indexed[path] = (blob, windows)
    return indexed


def _previous(window, current):
    start, end, text = window
    lines = text.splitlines()
    now = current[2].splitlines() if current else []
    excerpts = []
    for group in SequenceMatcher(None, lines, now, autojunk=False).get_grouped_opcodes(2):
        first, last = group[0][1], group[-1][2]
        if first < last:
            excerpts.append({'line': start + first, 'lines': lines[first:last]})
    return {'line_range': [start, end], 'excerpts': excerpts}


def change_review_instructions(before, after):
    """Return a prefix for one question, or an empty string for identical evidence."""
    old, new = _index(before), _index(after)
    if not old and not new:
        raise ValueError('Change review requires pinned source evidence')
    changes = []
    for path in sorted(old.keys() | new.keys()):
        old_blob, left = old.get(path, (None, {}))
        new_blob, right = new.get(path, (None, {}))
        if (old_blob, left) == (new_blob, right):
            continue
        windows = []
        for name in sorted(left.keys() | right.keys()):
            previous, current = left.get(name), right.get(name)
            if previous and current and previous[2] == current[2]:
                continue
            entry = {'name': name, 'status': ('absent_from_parent_windows' if previous is None
                     else 'absent_from_current_windows' if current is None else 'changed')}
            if previous is not None:
                entry['parent'] = _previous(previous, current)
            windows.append(entry)
        changes.append({'path': path, 'parent_blob': old_blob, 'current_blob': new_blob,
                        'outside_windows_uncertain': old_blob != new_blob,
                        'windows': windows})
    if not changes:
        return ''
    return (
        '이 질문의 범위에서 원고가 이전의 실패 상황과 현재 기대 결과 사이의 관찰 가능한 변화를 설명하는지 검토하세요. '
        '전제 조건과 계기, 영향을 받는 작업과 행위자, 관찰 지점, 기대 관찰값과 횟수·순서를 확인하세요. '
        '내부 처리 완료와 외부에서 확인되는 완료를 구분하고, 인접한 제어 동작의 역할도 확인하세요. '
        '이전에는 실패하고 현재에는 통과할 구체적인 회귀 검사와 판정 기준을 제시하세요. '
        '소스로 확인한 사실과 실제 기기에서 별도로 검증할 가설을 구분하세요. '
        '빠졌거나 오래된 주장은 각각 누락 또는 갱신이 필요한 항목으로 기록하고 적용 가능한 수정안을 제시하세요. '
        '구조화된 근거에는 현재 소스의 줄을 인용하고, 이전 줄을 언급할 때는 본문에서 이전 근거라고 명시하세요. '
        '아래 발췌는 이전 소스에 한정됩니다. 창에서 정의가 보이지 않거나 창 밖 변경 여부가 불확실하면 '
        '근거가 부족한 범위를 명시하고, 그 부분을 확인한 것으로 판정하지 마세요.\n'
        + json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    )
