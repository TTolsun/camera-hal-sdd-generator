"""Stage, verify and synchronize owned site artifacts; preserve unrelated files."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .config import Config

MANIFEST = "site-manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owned_path(root: Path, rel: str) -> Path:
    name = PurePosixPath(rel)
    target = (root / rel).resolve()
    if name.is_absolute() or ".." in name.parts or "\\" in rel or ":" in rel or not target.is_relative_to(root.resolve()):
        raise RuntimeError(f"Unsafe site artifact path: {rel}")
    return target


class Page(HTMLParser):
    def __init__(self, path: Path):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag in ("a", "link", "script", "img"):
            link = values.get("href", values.get("src"))
            if link:
                self.links.append(link)


def verify_site(root: Path, manifest: bool = True) -> dict:
    root = root.resolve()
    errors = []
    if manifest:
        data = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            raise RuntimeError("Unsupported site manifest schema")
        for rel, expected in data["outputs"].items():
            path = owned_path(root, rel)
            if not path.is_file() or digest(path) != expected:
                errors.append(f"Artifact changed or missing: {rel}")
        html_files = [owned_path(root, rel) for rel in data["outputs"] if rel.endswith(".html")]
    else:
        html_files = list(root.rglob("*.html"))
    pages = {p: Page(p) for p in html_files if p.exists()}
    for path, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f"Missing local target: {path.name} -> {link}")
            elif target in pages and url.fragment and unquote(url.fragment) not in pages[target].ids:
                errors.append(f"Missing anchor: {path.name} -> {link}")
    if errors:
        raise RuntimeError("Site verification failed:\n" + "\n".join(errors))
    return {"html_pages": len(pages), "broken_links": 0, "manifest_verified": manifest}


def build_site(cfg: Config, out: Path, render, mermaid_src: str | None) -> Path:
    out = out.resolve()
    source = cfg.sdd_dir.resolve()
    if out == source or out in source.parents or source in out.parents:
        raise RuntimeError("Site output must be separate from the Markdown source directory")
    cfg.build_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site-", dir=cfg.build_dir) as temporary:
        stage = Path(temporary).resolve()
        # TemporaryDirectory's recursive cleanup is restricted to this known workspace child.
        if stage.parent != cfg.build_dir.resolve():
            raise RuntimeError("Unexpected staging directory")
        render(cfg, stage, mermaid_src)
        verify_site(stage, manifest=False)
        outputs = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        inputs = {"sections": digest(cfg.sections_file)}
        inputs["configuration"] = hashlib.sha256(json.dumps(cfg.raw, sort_keys=True, default=str).encode()).hexdigest()
        intro = (cfg.raw.get("site") or {}).get("intro")
        if intro:
            inputs["intro"] = digest(cfg.root / intro)
        catalog = (cfg.raw.get("site") or {}).get("english_catalog")
        if catalog:
            inputs["english_catalog"] = digest(cfg.root / catalog)
        if cfg.facts_path.exists():
            inputs["facts"] = digest(cfg.facts_path)
        from .approvals import ledger_path
        if ledger_path(cfg).exists():
            inputs["approvals"] = digest(ledger_path(cfg))
        for p in sorted(cfg.sdd_dir.rglob("*.md")):
            inputs["markdown/" + p.relative_to(cfg.sdd_dir).as_posix()] = digest(p)
        code_root = Path(__file__).parent
        engine = {p.name: digest(p) for p in [code_root / "diagrams.py", code_root / "export_site.py",
                                            code_root / "document_health.py",
                                            code_root / "site_localization.py",
                                            code_root / "document_metadata.py", code_root / "scenario_document.py",
                                            code_root / "design_contracts.py", code_root / "evidence.py",
                                            Path(__file__)]}
        from .diagrams import POLICY_VERSION
        data = {"schema": 1, "diagram_policy": POLICY_VERSION, "inputs": inputs, "engine": engine,
                "dependencies": {name: version(name) for name in ("Markdown", "pymdown-extensions", "PyYAML")},
                "outputs": outputs}
        data["build_id"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        previous_file = out / MANIFEST
        previous = json.loads(previous_file.read_text(encoding="utf-8")) if previous_file.exists() else {"schema": 1, "outputs": {}}
        if previous.get("schema") != 1:
            raise RuntimeError("Unsupported previous site manifest")
        # Check every conflict and path before changing the destination.
        for rel, expected in previous["outputs"].items():
            path = owned_path(out, rel)
            if path.exists() and (not path.is_file() or digest(path) != expected):
                raise RuntimeError(f"Generated artifact was manually changed: {rel}; preserve/reconcile it before rebuilding")
        for rel in outputs:
            target = owned_path(out, rel)
            if rel not in previous["outputs"] and target.exists():
                raise RuntimeError(f"Unmanaged artifact would be overwritten: {rel}; preserve/reconcile it before rebuilding")
            for parent in target.parents:
                if parent.exists() and not parent.is_dir():
                    raise RuntimeError(f"Site output parent is not a directory: {parent}")
                if parent == out:
                    break
        out.mkdir(parents=True, exist_ok=True)
        for rel in outputs:
            target = owned_path(out, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / rel, target)
        for rel in previous["outputs"].keys() - outputs.keys():
            target = owned_path(out, rel)
            if target.is_file():
                target.unlink()  # Only files explicitly owned by the previous verified manifest.
        (out / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return out
