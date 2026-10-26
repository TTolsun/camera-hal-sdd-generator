import json
from pathlib import Path

import pytest

from sdd import state_io


def denied(winerror=None):
    error = PermissionError('State replacement denied')
    if winerror is not None:
        error.winerror = winerror
    return error


def test_transient_windows_replace_denial_keeps_old_state_until_success(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    path.write_text('{"old": true}', encoding='utf-8')
    original = Path.replace
    calls, sleeps = [], []
    def replace(source, target):
        calls.append(source)
        if len(calls) == 1:
            assert json.loads(path.read_text()) == {'old': True}
            raise denied(32)
        return original(source, target)
    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr(state_io.time, 'sleep', sleeps.append)
    state_io.save(path, {'new': True})
    assert len(calls) == 2 and sleeps == [.01]
    assert json.loads(path.read_text()) == {'new': True}


@pytest.mark.parametrize('winerror, attempts', [(5, 7), (None, 1)])
def test_persistent_or_other_permission_failure_is_not_hidden(tmp_path, monkeypatch, winerror, attempts):
    path = tmp_path / 'state.json'
    path.write_text('{"old": true}', encoding='utf-8')
    calls = []
    def replace(source, target):
        calls.append(source)
        raise denied(winerror)
    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr(state_io.time, 'sleep', lambda delay: None)
    with pytest.raises(PermissionError):
        state_io.save(path, {'new': True})
    assert len(calls) == attempts
    assert json.loads(path.read_text()) == {'old': True}
    assert json.loads(path.with_suffix('.tmp').read_text()) == {'new': True}
