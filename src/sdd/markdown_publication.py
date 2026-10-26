"""Publish Markdown to a dedicated Gerrit clone without replacing human pages.

This ownership manifest describes Markdown/Mermaid sources, not built site assets.
Run against an exclusive CI checkout; Git and directory renames are not a lock.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .config import Config, load, section_output
from .site_build import MANIFEST as SITE_MANIFEST, digest, owned_path

MANIFEST = "markdown-publication-manifest.json"


def _path(root: Path, rel: str) -> Path:
    # owned_path resolves links, so inspect lexical ancestors before using it.
    if not isinstance(rel, str) or not rel or PurePosixPath(rel).as_posix() != rel:
        raise RuntimeError(f"Invalid Markdown publication path: {rel}")
    target = root / rel
    for part in (target, *target.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise RuntimeError(f"Symlink/junction in publication path: {part}")
    result = owned_path(root, rel)
    if result == root.resolve() or ".git" in PurePosixPath(rel).parts:
        raise RuntimeError(f"Invalid Markdown publication path: {rel}")
    return result


def _inventory(root: Path, *, exclude: set[str] | None = None) -> dict[str, str]:
    if not root.exists():
        return {}
    _path(root.parent, root.name)
    if not root.is_dir():
        raise RuntimeError(f"Publication root is not a directory: {root}")
    result = {}
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root).as_posix()
        path = _path(root, rel)
        if exclude and rel in exclude:
            continue
        if path.is_file():
            result[rel] = digest(path)
        elif not path.is_dir():
            raise RuntimeError(f"Non-regular publication artifact: {rel}")
    return result


def manual_pages(cfg: Config, override: str | None = None) -> set[str]:
    if not cfg.sections_file.is_file():
        raise RuntimeError(f"Sections configuration is missing: {cfg.sections_file}")
    pages = {"index.md"}
    for section in cfg.sections():
        if section.get("kind") in {"manual", "index"}:
            pages.add(section_output(section))
    for rel in pages:
        _path(cfg.sdd_dir, rel)
        if not rel.endswith(".md"):
            raise RuntimeError(f"Manual page must be Markdown: {rel}")
    if override is not None and set(shlex.split(override)) != pages:
        raise RuntimeError("MANUAL_PAGES must exactly match configured manual/index pages: "
                           + ", ".join(sorted(pages)))
    return pages


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed ({result.returncode}): "
                           + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _staged(repo: Path) -> set[str]:
    return {os.fsdecode(p) for p in _git(repo, "diff", "--cached", "--name-only", "-z").split(b"\0") if p}


def _literal(paths: set[str]) -> list[str]:
    return [f":(literal){p}" for p in sorted(paths)]


@contextmanager
def _workspace(repo: Path):
    temporary = Path(tempfile.mkdtemp(prefix="sdd-markdown-", dir=repo))
    try:
        yield temporary / "new", temporary / "previous"
    except BaseException as exc:
        # Do not delete the only previous copy if restoring a rename also fails.
        if (temporary / "previous").exists():
            raise RuntimeError(f"Publication rollback incomplete; previous docs preserved at {temporary / 'previous'}") from exc
        shutil.rmtree(temporary)
        raise
    else:
        shutil.rmtree(temporary)


def synchronize(cfg: Config, repo: Path, override: str | None = None) -> set[str]:
    """Validate, prepare all bytes, replace with rollback, and stage exact paths.

    Existing unknown files remain untouched. On first use, a generated-path
    collision is adopted only when its bytes already equal the new source.
    """
    _path(repo.parent, repo.name)
    repo = repo.resolve()
    if Path(os.fsdecode(_git(repo, "rev-parse", "--show-toplevel")).strip()).resolve() != repo:
        raise RuntimeError("DOCS_DIR must be the Git checkout root")
    _git(repo, "rev-parse", "--verify", "HEAD")
    if _staged(repo):
        raise RuntimeError("Unexpected staged changes in docs checkout")
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--", ":(literal)sdd"):
        raise RuntimeError("Docs sdd/ has local changes; preserve/reconcile them first")
    source = cfg.sdd_dir
    out = _path(repo, "sdd")
    if source.resolve() == out or source.resolve() in out.parents or out in source.resolve().parents:
        raise RuntimeError("Markdown source and publication directory must be separate")
    manual = manual_pages(cfg, override)
    preserved = manual | {"approvals.json"}
    incoming, before = _inventory(source, exclude={"approvals.lock"}), _inventory(out)
    if not incoming:
        raise RuntimeError("Markdown source is empty or missing")
    if SITE_MANIFEST in incoming or SITE_MANIFEST in before:
        raise RuntimeError("site-manifest.json belongs to built HTML publication, not Markdown")
    for rel in incoming:
        if PurePosixPath(rel).name == ".gitkeep":
            continue
        if rel == MANIFEST or (rel != "approvals.json" and Path(rel).suffix not in {".md", ".mmd"}):
            raise RuntimeError(f"Unsupported Markdown publication artifact: {rel}")
    incoming = {p: sha for p, sha in incoming.items() if PurePosixPath(p).name != ".gitkeep"}
    old = {}
    if MANIFEST in before:
        prior = json.loads(_path(out, MANIFEST).read_text(encoding="utf-8"))
        if prior.get("schema") != 1 or prior.get("kind") != "sdd-markdown":
            raise RuntimeError("Unsupported Markdown publication manifest")
        old = prior.get("outputs")
        if not isinstance(old, dict):
            raise RuntimeError("Invalid Markdown publication outputs")
        for rel, sha in old.items():
            _path(out, rel)
            if rel == MANIFEST or Path(rel).suffix not in {".md", ".mmd"} or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise RuntimeError(f"Invalid Markdown ownership entry: {rel}")
    generated = {p: sha for p, sha in incoming.items() if p not in preserved}
    for rel in old.keys() | generated.keys():
        _path(out, rel)
        if rel in preserved:
            continue
        if rel in old and before.get(rel) != old[rel]:
            raise RuntimeError(f"Published generated file changed or missing: {rel}")
        if rel not in old and rel in before and before[rel] != generated[rel]:
            raise RuntimeError(f"Unmanaged Markdown publication conflict: {rel}")
    # Everything, including manual and unrelated files, is copied before out moves.
    # A failed copy therefore leaves the previous directory byte-for-byte intact.
    with _workspace(repo) as (stage, backup):
        if out.exists():
            shutil.copytree(out, stage)
        else:
            stage.mkdir()
        for rel in old.keys() - generated.keys() - preserved:
            _path(stage, rel).unlink()
        for rel in generated.keys() | (incoming.keys() & preserved - before.keys()):
            target = _path(stage, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_path(source, rel), target)
            if digest(target) != incoming[rel]:
                raise RuntimeError(f"Markdown changed while copying: {rel}")
        data = {"schema": 1, "kind": "sdd-markdown", "manual_pages": sorted(manual),
                "outputs": dict(sorted(generated.items()))}
        (stage / MANIFEST).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        after = _inventory(stage)
        changed = {f"sdd/{p}" for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
        if not changed:
            return set()
        # Detect a changed checkout before the first mutation, too.
        if _staged(repo) or _inventory(out) != before:
            raise RuntimeError("Docs checkout changed during publication preparation")
        moved = False
        try:
            if out.exists():
                out.rename(backup)
            stage.rename(out)
            moved = True
            _git(repo, "add", "--", *_literal(changed))
            if _staged(repo) != changed:
                raise RuntimeError("Unexpected staged changes after Markdown publication")
        except BaseException:
            if moved:
                out.rename(stage)
            if backup.exists():
                backup.rename(out)
            _git(repo, "reset", "-q", "HEAD", "--", *_literal(changed))
            raise
        return changed


def commit_and_push(repo: Path, changed: set[str], subject: str, body: str, remote: str, ref: str) -> bool:
    if not changed:
        return False
    if _staged(repo) != changed or any(not p.startswith("sdd/") for p in changed):
        raise RuntimeError("Unexpected staged changes before docs commit")
    # Explicit paths also exclude an unrelated index change arriving at commit time.
    _git(repo, "commit", "-q", "-m", subject, "-m", body, "--only", "--", *_literal(changed))
    _git(repo, "push", "-q", "--", remote, f"HEAD:{ref}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--push-ref", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()
    _git(args.docs_dir, "check-ref-format", args.push_ref)
    body = args.body_file.read_text(encoding="utf-8")[:4000] if args.body_file.is_file() else "(변경 요약 없음)"
    changed = synchronize(load(args.config), args.docs_dir, os.environ.get("MANUAL_PAGES"))
    published = commit_and_push(args.docs_dir, changed, args.subject, body, args.remote, args.push_ref)
    print("Markdown docs committed and pushed" if published else "Markdown docs unchanged; no commit or push")


if __name__ == "__main__":
    main()
