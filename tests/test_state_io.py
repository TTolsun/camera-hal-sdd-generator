"""Atomic state replacement preserves committed JSON through failed writes."""

import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdd import state_io


def _denied(winerror):
    error = PermissionError("replacement denied")
    if winerror is not None:
        error.winerror = winerror
    return error


def test_default_serialization_and_return_value(tmp_path):
    path = tmp_path / "new" / "state.json"
    data = {"z": "한글", "schema": 1, "a": {"last": False}}
    assert state_io.save(path, data) is None
    expected = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    assert path.read_bytes() == expected.replace("\n", os.linesep).encode("utf-8")
    assert list(path.parent.iterdir()) == [path]


def test_replacement_observes_old_json_and_complete_prepared_json(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    state_io.save(path, {"old": True})
    replace = Path.replace

    def inspect(temporary, destination):
        assert destination == path
        assert temporary.parent == destination.parent
        assert json.loads(destination.read_text(encoding="utf-8")) == {"old": True}
        assert json.loads(temporary.read_text(encoding="utf-8")) == {"new": "완료"}
        return replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", inspect)
    state_io.save(path, {"new": "완료"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": "완료"}
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("failure", ["serialize", "write", "replace"])
def test_failure_preserves_previous_json_and_cleans_temporary(tmp_path, monkeypatch, failure):
    path = tmp_path / "state.json"
    state_io.save(path, {"old": "보존"})
    original = path.read_bytes()
    data = {"new": True}
    if failure == "serialize":
        data["bad"] = object()
    elif failure == "write":
        create = state_io.tempfile.NamedTemporaryFile

        @contextmanager
        def failing_writer(**kwargs):
            with create(**kwargs) as stream:
                class PartialWriter:
                    name = stream.name

                    def write(self, text):
                        stream.write(text[:4])
                        raise OSError("disk write failed")

                yield PartialWriter()

        monkeypatch.setattr(state_io.tempfile, "NamedTemporaryFile", failing_writer)
    else:
        def fail_replace(temporary, destination):
            raise OSError("replace failed")

        monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises((TypeError, OSError)):
        state_io.save(path, data)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("winerror", [5, 32, 33])
@pytest.mark.parametrize("permanent", [False, True])
def test_windows_denial_retries_prepared_file_with_bounded_delays(
        tmp_path, monkeypatch, winerror, permanent):
    path = tmp_path / "state.json"
    state_io.save(path, {"old": True})
    original = path.read_bytes()
    replace = Path.replace
    attempts = []
    sleeps = []

    def denied(temporary, destination):
        attempts.append(temporary)
        assert destination.read_bytes() == original
        assert json.loads(temporary.read_text(encoding="utf-8")) == {"new": True}
        if permanent or len(attempts) < 3:
            raise _denied(winerror)
        return replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(state_io.time, "sleep", sleeps.append)
    if permanent:
        with pytest.raises(PermissionError):
            state_io.save(path, {"new": True})
        assert path.read_bytes() == original
        assert len(attempts) == 7
        assert sleeps == [.01, .025, .05, .1, .2, .4]
    else:
        state_io.save(path, {"new": True})
        assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
        assert len(attempts) == 3
        assert sleeps == [.01, .025]
    assert len(set(attempts)) == 1
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("winerror", [None, 2, 13])
def test_other_permission_errors_are_not_retried(tmp_path, monkeypatch, winerror):
    path = tmp_path / "state.json"
    state_io.save(path, {"old": True})
    original = path.read_bytes()
    attempts = []
    sleeps = []

    def denied(temporary, destination):
        attempts.append(temporary)
        raise _denied(winerror)

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(state_io.time, "sleep", sleeps.append)
    with pytest.raises(PermissionError):
        state_io.save(path, {"new": True})
    assert len(attempts) == 1 and sleeps == []
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_overlapping_saves_and_stale_temporary_do_not_collide(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    stale = path.with_suffix(".tmp")
    stale.write_text("unrelated leftover", encoding="utf-8")
    replace = Path.replace
    prepared = []

    def overlapping(temporary, destination):
        prepared.append(temporary)
        if len(prepared) == 1:
            state_io.save(path, {"inner": True})
            assert json.loads(path.read_text(encoding="utf-8")) == {"inner": True}
        return replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", overlapping)
    state_io.save(path, {"outer": True})
    assert len(set(prepared)) == 2
    assert json.loads(path.read_text(encoding="utf-8")) == {"outer": True}
    assert stale.read_text(encoding="utf-8") == "unrelated leftover"
    assert set(tmp_path.iterdir()) == {path, stale}


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
    assert list(tmp_path.glob('.state.json.*.tmp')) == []
