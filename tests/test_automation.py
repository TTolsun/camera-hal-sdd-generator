import json
import subprocess
import sys
from pathlib import Path

import pytest

from sdd import automation, update
from sdd.facts.model import KnowledgeModel
from sdd.site_build import digest


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, encoding="utf-8").strip()


def init(repo):
    repo.mkdir(exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("seed")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "seed")


@pytest.fixture
def pipeline(tmp_cfg, tmp_path, monkeypatch):
    init(tmp_cfg.source_root)
    seed = tmp_path / "seed"
    init(seed)
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(seed), str(remote))
    repo = tmp_path / "docs"
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    tmp_cfg.raw["automation"] = {
        "to": "main", "fetch": False,
        "publish": {"repo": str(repo), "directory": "docs", "remote": "origin", "branch": "main",
                    "verify_command": [sys.executable, "-c", "pass"]}}
    calls = []

    def run_update(cfg, to, **kwargs):
        calls.append(to)
        KnowledgeModel(meta={"source_commit": to}).save(cfg.facts_path)
        return update.Result()

    def export(cfg, out):
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text("<html><body>test</body></html>")
        (out / "site-manifest.json").write_text(json.dumps({
            "schema": 1, "build_id": "test-build", "outputs": {"index.html": digest(out / "index.html")}}))
        return out
    monkeypatch.setattr(update, "run_update", run_update)
    monkeypatch.setattr(automation, "export_site", export)
    return tmp_cfg, repo, remote, calls


def test_publish_and_no_change_does_not_create_commit(pipeline):
    cfg, repo, remote, calls = pipeline
    assert automation.run(cfg) == 0
    state = json.loads((cfg.build_dir / "automation-state.json").read_text())
    assert "pending" not in state
    assert state["last_published"]["docs_commit"] == git(remote, "rev-parse", "main")
    first = git(repo, "rev-parse", "HEAD")
    assert automation.run(cfg) == 0
    assert first == git(repo, "rev-parse", "HEAD")


def test_verification_retry_keeps_same_target_even_after_new_source_commit(pipeline):
    cfg, repo, remote, calls = pipeline
    marker = cfg.root / "ready"
    cfg.raw["automation"]["publish"]["verify_command"] = [
        sys.executable, "-c", "import pathlib,sys;sys.exit(0 if pathlib.Path(sys.argv[1]).exists() else 7)", str(marker)]
    with pytest.raises(subprocess.CalledProcessError):
        automation.run(cfg)
    state = json.loads((cfg.build_dir / "automation-state.json").read_text())
    assert state["pending"]["phase"] == "verify"
    assert "last_published" not in state
    first = state["pending"]["target"]
    (cfg.source_root / "new.txt").write_text("new")
    git(cfg.source_root, "add", ".")
    git(cfg.source_root, "commit", "-qm", "new")
    marker.touch()
    # Schedule edits do not invalidate an in-flight publication.
    cfg.raw["automation"]["schedule"] = {"time": "22:15", "timezone": "Asia/Seoul"}
    assert automation.run(cfg) == 0
    assert calls == [first]
    state = json.loads((cfg.build_dir / "automation-state.json").read_text())
    assert state["last_published"]["target"] == first


def test_push_retry_does_not_regenerate(pipeline, monkeypatch):
    cfg, repo, remote, calls = pipeline
    real = automation.git
    def broken(repo, *args):
        if args[0] == "push":
            raise RuntimeError("offline")
        return real(repo, *args)
    monkeypatch.setattr(automation, "git", broken)
    with pytest.raises(RuntimeError, match="offline"):
        automation.run(cfg)
    commit = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(automation, "git", real)
    assert automation.run(cfg) == 0
    assert len(calls) == 1 and git(repo, "rev-parse", "HEAD") == commit


def test_review_gate_never_builds_or_pushes(pipeline, monkeypatch):
    cfg, repo, remote, calls = pipeline
    before = git(remote, "rev-parse", "HEAD")
    monkeypatch.setattr(update, "run_update", lambda *a, **k: update.Result(exit_code=2, stopped_reason="review"))
    assert automation.run(cfg) == 2
    assert not (repo / "docs").exists()
    assert git(remote, "rev-parse", "HEAD") == before


def test_crash_after_commit_recovers_without_duplicate_commit(pipeline, monkeypatch):
    cfg, repo, remote, calls = pipeline
    real = automation.git
    def crash(repo, *args):
        result = real(repo, *args)
        if args[0] == "commit":
            raise RuntimeError("crash after commit")
        return result
    monkeypatch.setattr(automation, "git", crash)
    with pytest.raises(RuntimeError, match="crash after commit"):
        automation.run(cfg)
    first = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(automation, "git", real)
    assert automation.run(cfg) == 0
    assert git(repo, "rev-parse", "HEAD") == first
    assert len(calls) == 1


def test_dirty_clone_and_existing_unpushed_commit_are_rejected(pipeline):
    cfg, repo, remote, calls = pipeline
    (repo / "personal").write_text("keep")
    with pytest.raises(RuntimeError, match="기존 변경"):
        automation.run(cfg)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "personal")
    with pytest.raises(RuntimeError, match="미게시 커밋"):
        automation.run(cfg)
    assert calls == []


def test_lock_rejects_concurrent_run_and_releases(tmp_path):
    path = tmp_path / "lock"
    with automation.locked(path):
        with pytest.raises(RuntimeError, match="이미 실행"):
            with automation.locked(path):
                pass
    with automation.locked(path):
        pass


def test_custom_schedule_and_escaping(tmp_cfg):
    tmp_cfg.raw["automation"] = {"schedule": {"time": "07:35", "timezone": "Asia/Seoul",
        "command": ["/opt/sdd/bin/sdd", "--config", "{config}", "automate"]}}
    result = automation.cron(tmp_cfg, Path("/private/my project/100%/sdd.yaml"))
    assert "CRON_TZ=Asia/Seoul\n35 7 * * *" in result
    assert "100\\%" in result and "'" in result
    tmp_cfg.raw["automation"]["schedule"]["time"] = "24:01"
    with pytest.raises(ValueError, match="HH:MM"):
        automation.cron(tmp_cfg, tmp_cfg.root / "sdd.yaml")


def test_copy_preserves_manual_files_and_rejects_edits(tmp_path):
    from sdd.publication import copy_site
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage.mkdir()
    out.mkdir()
    (stage / "index.html").write_text("new")
    (stage / "site-manifest.json").write_text(json.dumps({"schema": 1, "outputs": {
        "index.html": digest(stage / "index.html")}}))
    (out / "CNAME").write_text("internal")
    copy_site(stage, out)
    copy_site(stage, out)
    assert (out / "CNAME").read_text() == "internal"
    (out / "index.html").write_text("manual edit")
    with pytest.raises(RuntimeError, match="수동"):
        copy_site(stage, out)


def test_actual_http_publication_verification(tmp_path):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from sdd.publication import verify_remote
    (tmp_path / "index.html").write_text("<html>published</html>")
    (tmp_path / "site-manifest.json").write_text(json.dumps({"schema": 1, "build_id": "actual",
        "outputs": {"index.html": digest(tmp_path / "index.html")}}))
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        assert verify_remote(tmp_path, url, timeout=5, interval=0.01) == "actual"
        # Serve another valid build: HTTP 200 must not count as publication success.
        local = tmp_path / "expected"
        local.mkdir()
        (local / "index.html").write_text("<html>expected</html>")
        (local / "site-manifest.json").write_text(json.dumps({"schema": 1, "build_id": "expected",
            "outputs": {"index.html": digest(local / "index.html")}}))
        with pytest.raises(RuntimeError, match="게시 확인 실패"):
            verify_remote(local, url, timeout=0.1, interval=0.01)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
