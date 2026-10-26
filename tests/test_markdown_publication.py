"""Local Git tests for the Gerrit Markdown example; no Gerrit service is used."""

import json
import shutil
import subprocess
from dataclasses import replace

import pytest
import yaml

from sdd import markdown_publication as pub


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def write(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def publication(tmp_cfg, tmp_path):
    cfg = replace(tmp_cfg, sdd_dir=tmp_path / "source")
    cfg.sections_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [
        {"id": "index", "kind": "index"},
        {"id": "human", "kind": "manual", "output": "notes/deep/human.md"},
        {"id": "overview", "kind": "prose"},
    ]}), encoding="utf-8")
    write(cfg.sdd_dir, "index.md", "generated index")
    write(cfg.sdd_dir, "notes/deep/human.md", "manual scaffold")
    write(cfg.sdd_dir, "overview.md", "generated v1")
    write(cfg.sdd_dir, "diagrams/a.mmd", "flowchart LR\nA --> B")
    write(cfg.sdd_dir, "diagrams/.gitkeep", "")
    repo = tmp_path / "docs"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    write(repo, "README.md", "outside publication")
    write(repo, "sdd/index.md", "human index")
    write(repo, "sdd/notes/deep/human.md", "human decision")
    write(repo, "sdd/unrelated.txt", "keep")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "initial")
    return cfg, repo


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def publish_commit(cfg, repo):
    changed = pub.synchronize(cfg, repo)
    git(repo, "commit", "-q", "-m", "publish")
    return changed


def test_preserves_nested_manual_and_unrelated_and_removes_owned_stale(publication):
    cfg, repo = publication
    changed = publish_commit(cfg, repo)
    assert "sdd/overview.md" in changed
    assert (repo / "sdd/index.md").read_text() == "human index"
    assert (repo / "sdd/notes/deep/human.md").read_text() == "human decision"
    assert (repo / "sdd/unrelated.txt").read_text() == "keep"
    assert (repo / "README.md").read_text() == "outside publication"
    manifest = json.loads((repo / "sdd" / pub.MANIFEST).read_text())
    assert set(manifest["outputs"]) == {"overview.md", "diagrams/a.mmd"}
    assert "notes/deep/human.md" in manifest["manual_pages"]
    (cfg.sdd_dir / "diagrams/a.mmd").unlink()
    write(cfg.sdd_dir, "overview.md", "generated v2")
    pub.synchronize(cfg, repo)
    assert not (repo / "sdd/diagrams/a.mmd").exists()
    assert (repo / "sdd/unrelated.txt").exists()


def test_no_change_no_commit_or_push(publication, monkeypatch):
    cfg, repo = publication
    publish_commit(cfg, repo)
    original = git(repo, "rev-parse", "HEAD")
    changed = pub.synchronize(cfg, repo)
    assert changed == set()
    monkeypatch.setattr(pub, "_git", lambda *a: pytest.fail("No Git mutation on unchanged publication"))
    assert not pub.commit_and_push(repo, changed, "unused", "", "unused", "unused")
    assert git(repo, "rev-parse", "HEAD") == original


@pytest.mark.parametrize("where", ["source-copy", "existing-copy", "stage-add", "install-rename"])
def test_failures_preserve_all_previous_files(publication, monkeypatch, where):
    cfg, repo = publication
    publish_commit(cfg, repo)
    write(cfg.sdd_dir, "overview.md", "generated v2")
    before = snapshot(repo / "sdd")
    if where == "source-copy":
        def fail(*args, **kwargs):
            raise OSError("copy failed")
        monkeypatch.setattr(shutil, "copyfile", fail)
    elif where == "existing-copy":
        monkeypatch.setattr(shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(OSError("copy failed")))
    elif where == "stage-add":
        real = pub._git
        def fail_add(repo, *args):
            if args[0] == "add":
                raise OSError("git add failed")
            return real(repo, *args)
        monkeypatch.setattr(pub, "_git", fail_add)
    else:
        real = type(repo).rename
        def fail_rename(self, target):
            if self.name == "new":
                raise OSError("rename failed")
            return real(self, target)
        monkeypatch.setattr(type(repo), "rename", fail_rename)
    with pytest.raises((OSError, shutil.Error)):
        pub.synchronize(cfg, repo)
    assert snapshot(repo / "sdd") == before
    assert pub._staged(repo) == set()
    assert not list(repo.glob("sdd-markdown-*"))


def test_env_manual_list_must_match_config(publication):
    cfg, repo = publication
    with pytest.raises(RuntimeError, match="MANUAL_PAGES"):
        pub.synchronize(cfg, repo, "index.md constraints.md decisions.md")
    assert pub.synchronize(cfg, repo, "index.md notes/deep/human.md")


@pytest.mark.parametrize("rel", ["../outside.md", "/outside.md", "notes\\outside.md", "C:/outside.md", "./other.md"])
def test_config_path_escape_is_rejected(publication, rel):
    cfg, repo = publication
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [{"id": "bad", "kind": "manual", "output": rel}]}))
    before = snapshot(repo / "sdd")
    with pytest.raises(RuntimeError):
        pub.synchronize(cfg, repo)
    assert snapshot(repo / "sdd") == before


@pytest.mark.parametrize("where", ["source", "destination"])
def test_symlinks_are_rejected(publication, tmp_path, where):
    cfg, repo = publication
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    write(elsewhere, "private.md", "do not publish")
    link = (cfg.sdd_dir if where == "source" else repo / "sdd") / "link"
    try:
        link.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        import os
        if os.name != "nt":
            raise
        # Directory junctions cover the Windows reparse-point escape as well.
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(elsewhere)], capture_output=True)
        if result.returncode:
            pytest.skip("Host does not permit symlink or junction creation")
    with pytest.raises(RuntimeError):
        pub.synchronize(cfg, repo)
    assert (elsewhere / "private.md").read_text() == "do not publish"


def test_missing_section_config_is_rejected(publication):
    cfg, repo = publication
    cfg.sections_file.unlink()
    with pytest.raises(RuntimeError, match="configuration is missing"):
        pub.synchronize(cfg, repo)


@pytest.mark.parametrize("existing", [False, True])
def test_approval_ledger_bytes_preserved_and_runtime_lock_excluded(publication, existing):
    cfg, repo = publication
    ledger = b'{"schema": 1, "approvals": {"source": "input ledger"}}\r\n'
    (cfg.sdd_dir / "approvals.json").write_bytes(ledger)
    write(cfg.sdd_dir, "approvals.lock", "runtime lock, never publish")
    if existing:
        ledger = b'{"schema": 1, "approvals": {"docs": "original ledger"}}\n'
        (repo / "sdd/approvals.json").write_bytes(ledger)
        git(repo, "add", "sdd/approvals.json")
        git(repo, "commit", "-q", "-m", "existing approval ledger")
    changed = publish_commit(cfg, repo)
    assert (repo / "sdd/approvals.json").read_bytes() == ledger
    assert not (repo / "sdd/approvals.lock").exists()
    assert ("sdd/approvals.json" in changed) is not existing
    manifest = json.loads((repo / "sdd" / pub.MANIFEST).read_text())
    assert "approvals.json" not in manifest["outputs"]
    (cfg.sdd_dir / "approvals.json").write_bytes(b'{"different": true}')
    assert pub.synchronize(cfg, repo) == set()
    assert (repo / "sdd/approvals.json").read_bytes() == ledger


def test_other_json_remains_unsupported(publication):
    cfg, repo = publication
    write(cfg.sdd_dir, "unknown.json", "{}")
    with pytest.raises(RuntimeError, match="Unsupported Markdown publication artifact"):
        pub.synchronize(cfg, repo)


def test_failed_rollback_keeps_recovery_copy(publication, monkeypatch):
    cfg, repo = publication
    publish_commit(cfg, repo)
    write(cfg.sdd_dir, "overview.md", "new version")
    before = snapshot(repo / "sdd")
    real_rename, real_git = type(repo).rename, pub._git
    def fail_restore(self, target):
        if self.name == "previous":
            raise OSError("restore failed")
        return real_rename(self, target)
    def fail_add(repo, *args):
        if args[0] == "add":
            raise OSError("add failed")
        return real_git(repo, *args)
    monkeypatch.setattr(type(repo), "rename", fail_restore)
    monkeypatch.setattr(pub, "_git", fail_add)
    with pytest.raises(RuntimeError, match="previous docs preserved"):
        pub.synchronize(cfg, repo)
    recovery, = repo.glob("sdd-markdown-*/previous")
    assert snapshot(recovery) == before


def test_unexpected_staged_file_is_protected_before_copy_and_commit(publication):
    cfg, repo = publication
    write(repo, "README.md", "staged outside")
    git(repo, "add", "README.md")
    before = snapshot(repo / "sdd")
    with pytest.raises(RuntimeError, match="staged"):
        pub.synchronize(cfg, repo)
    assert snapshot(repo / "sdd") == before
    git(repo, "reset", "-q", "HEAD", "--", "README.md")
    changed = pub.synchronize(cfg, repo)
    git(repo, "add", "README.md")
    original = git(repo, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="staged"):
        pub.commit_and_push(repo, changed, "docs", "", "unused", "refs/for/main")
    assert git(repo, "rev-parse", "HEAD") == original


def test_outside_unstaged_and_untracked_files_are_not_committed(publication, tmp_path):
    cfg, repo = publication
    write(repo, "README.md", "unstaged outside")
    write(repo, "private.log", "untracked outside")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    changed = pub.synchronize(cfg, repo)
    assert pub.commit_and_push(repo, changed, "docs", "body", str(remote), "refs/for/main")
    committed = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").decode().splitlines()
    assert all(p.startswith("sdd/") for p in committed)
    assert (repo / "README.md").read_text() == "unstaged outside"
    assert (repo / "private.log").read_text() == "untracked outside"
    assert git(remote, "rev-parse", "refs/for/main") == git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("mode", ["unmanaged", "edited-owned", "deleted-owned", "site-source", "site-target", "html-source", "dirty-manual"])
def test_conflicting_content_is_not_overwritten(publication, mode):
    cfg, repo = publication
    if mode in {"edited-owned", "deleted-owned"}:
        publish_commit(cfg, repo)
        if mode == "edited-owned":
            write(repo, "sdd/overview.md", "human changed generated file")
        else:
            (repo / "sdd/overview.md").unlink()
        git(repo, "add", "sdd")
        git(repo, "commit", "-q", "-m", "manual change")
    elif mode == "unmanaged":
        write(repo, "sdd/overview.md", "unknown old document")
        git(repo, "add", "sdd")
        git(repo, "commit", "-q", "-m", "old docs")
    elif mode == "dirty-manual":
        write(repo, "sdd/notes/deep/human.md", "uncommitted human change")
    elif mode == "site-target":
        write(repo, "sdd/site-manifest.json", "{}")
        git(repo, "add", "sdd")
        git(repo, "commit", "-q", "-m", "site")
    else:
        write(cfg.sdd_dir, "site-manifest.json" if mode == "site-source" else "index.html", "{}")
    before = snapshot(repo / "sdd")
    with pytest.raises(RuntimeError):
        pub.synchronize(cfg, repo)
    assert snapshot(repo / "sdd") == before
