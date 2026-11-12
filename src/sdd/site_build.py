"""Stage, verify and synchronize owned site artifacts; preserve unrelated files."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import Config
from .site_paths import owned_path
from .validation_stage import verify as verify_inputs, current
from .validation_execution import staged

MANIFEST = "site-manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Page(HTMLParser):
    def __init__(self, path: Path):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.repeated_id_attributes = False
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        values = {}
        for name, value in attrs:
            if name in values:
                if name == 'id':
                    self.repeated_id_attributes = True
                continue
            # Browsers retain the first occurrence of an HTML attribute.
            values[name] = value
        if "id" in values:
            if values['id'] in self.ids:
                self.duplicate_ids.add(values['id'])
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
        if page.repeated_id_attributes:
            errors.append(f"Repeated id attribute: {path.name}")
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f"Missing local target: {path.name} -> {link}")
            elif target in pages and url.fragment:
                # HTML resolves a literal fragment ID before its decoded form.
                from .site_fragments import fragment_id
                anchor = fragment_id(url.fragment, pages[target].ids)
                if anchor not in pages[target].ids:
                    errors.append(f"Missing anchor: {path.name} -> {link}")
                elif anchor in pages[target].duplicate_ids:
                    errors.append(f"Ambiguous anchor: {path.name} -> {link}")
    if errors:
        raise RuntimeError("Site verification failed:\n" + "\n".join(errors))
    if manifest:
        from .visual_audit import verify_published
        verify_published(root, data)
    return {"html_pages": len(pages), "broken_links": 0, "manifest_verified": manifest}


@staged
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
        from .visual_audit import publication_gate, verify_published
        publication_gate(cfg, stage)
        outputs = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        inputs = {"sections": digest(cfg.sections_file)}
        from .visual_audit import policy as audit_policy
        audit_settings = audit_policy(cfg)
        audit_file = audit_settings.get('reviews')
        if audit_settings.get('enabled', False) and audit_file:
            inputs['item_visual_reviews'] = digest(cfg.root / audit_file)
        if audit_settings.get('enabled',False) and audit_settings.get('baseline'):
            inputs['item_visual_baseline'] = digest(cfg.root/audit_settings['baseline']['file'])
            from .visual_audit import REPORT, digest as audit_digest
            inputs['item_visual_retention'] = audit_digest(json.loads((stage/REPORT).read_bytes())['baseline_retention'])
        from .render_profiles import inputs as editorial_inputs
        inputs.update({'editorial/'+key:value for key,value in editorial_inputs(cfg).items()})
        from .product_context import input_paths
        for index, path in enumerate(input_paths(cfg)):
            inputs[f'products/{index}'] = digest(path)
        inputs["configuration"] = hashlib.sha256(json.dumps(cfg.raw, sort_keys=True, default=str).encode()).hexdigest()
        if cfg.paths.get('consistency_file'):
            inputs['consistency_configuration'] = digest(cfg.paths['consistency_file'])
            inputs['consistency_review'] = digest(cfg.build_dir/'consistency-review.json')
        intro = cfg.site.intro
        if intro:
            inputs["intro"] = digest(cfg.root / intro)
        if cfg.site.guide_visuals:
            inputs['guide_visuals'] = digest(cfg.root / cfg.site.guide_visuals)
        catalog = cfg.site.english_catalog
        if catalog:
            inputs["english_catalog"] = digest(cfg.root / catalog)
        if cfg.facts_path.exists():
            inputs["facts"] = digest(cfg.facts_path)
        visuals_file = cfg.visuals.file
        if visuals_file:
            inputs['visuals'] = digest(cfg.root / visuals_file)
        from .approvals import ledger_path
        if ledger_path(cfg).exists():
            inputs["approvals"] = digest(ledger_path(cfg))
        for p in sorted(cfg.sdd_dir.rglob("*.md")):
            inputs["markdown/" + p.relative_to(cfg.sdd_dir).as_posix()] = digest(p)
        code_root = Path(__file__).parent
        engine = {p.name: digest(p) for p in [code_root / "diagrams.py", code_root / "visuals.py", code_root / "export_site.py",
                                            code_root / "document_health.py", code_root / "evidence_navigation.py",
                                            code_root / "site_localization.py", code_root / "site_markdown.py",
                                            code_root / "source_links.py",
                                            code_root / "index_navigation.py", code_root / "reading_cleanup.py",
                                            code_root / "document_metadata.py", code_root / "scenario_document.py",
                                            code_root / "scenario_sections.py", code_root / "scenario_ownership.py",
                                            code_root / "source_identity.py", code_root / "translation_context.py",
                                            code_root / "consistency_profile.py", code_root / "next_steps.py",
                                            code_root / "design_contracts.py", code_root / "evidence.py",
                                            code_root / "contract_schema.py", code_root / "explanation.py", code_root / "reader_profiles.py",
                                            code_root / "reader_scope.py", code_root / "product_context.py",
                                            code_root / "contract_render.py", code_root / "markdown_text.py",
                                            code_root / "generated_design.py", code_root / "generated_visuals.py",
                                            code_root / "config.py", code_root / "render_profiles.py", code_root / "design_types.py",
                                            code_root / "validation_stage.py", code_root / "input_watch.py", code_root / "publication_plan.py",
                                            code_root / "publication_operation.py",
                                            code_root / "publication_reports.py",
                                            code_root / "validation_execution.py", code_root / "visual_audit.py", code_root / "visual_dom.py", code_root / "visual_presentation.py", code_root / "site_fragments.py", code_root / "site_paths.py", code_root / "mermaid_text.py",
                                            code_root / "execution_lock.py", code_root / "generation_run.py", code_root / "guide_visuals.py",
                                            code_root / "consistency.py", code_root / "consistency_sources.py",
                                            code_root / "consistency_analysis.py", code_root / "cli_schema.py",
                                            code_root / "design_request.py", code_root / "design_response.py",
                                            code_root / "design_checkpoint.py",
                                            code_root / "design_execution.py", code_root / "design_trials.py",
                                            code_root / "design_compat.py",
                                            Path(__file__)]}
        from .diagrams import POLICY_VERSION
        data = {"schema": 1, "diagram_policy": POLICY_VERSION, "inputs": inputs, "engine": engine,
                "dependencies": {name: version(name) for name in ("Markdown", "pymdown-extensions", "PyYAML", "html5lib")},
                "outputs": outputs}
        data["build_id"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        verify_published(stage, data)
        from .generation_run import observed
        execution = observed()
        if execution is not None and execution.publication_contract is not None:
            execution.publication_contract.begin_output()
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
        verify_inputs()
        # Keep original owned bytes until the outermost validation accepts its
        # inputs. Even an edit during destination copying rolls back the site.
        backups = {rel: owned_path(out, rel).read_bytes() if owned_path(out, rel).is_file() else None
                   for rel in previous['outputs'].keys() | outputs.keys() | {MANIFEST}}
        produced = {}
        def rollback():
            for rel, expected in produced.items():
                target = owned_path(out, rel)
                actual = target.read_bytes() if target.is_file() else None
                if actual != expected:
                    if execution is not None:
                        execution.report.setdefault('rollback_conflicts', []).append(str(target))
                    continue
                raw = backups[rel]
                if raw is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
        current().rollbacks.append(rollback)
        out.mkdir(parents=True, exist_ok=True)
        for rel in outputs:
            target = owned_path(out, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            # A failed copy must not truncate the currently published file.
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.sdd-', delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copyfile(stage / rel, temporary)
                temporary.replace(target)
                produced[rel] = (stage / rel).read_bytes()
            finally:
                temporary.unlink(missing_ok=True)
        for rel in previous["outputs"].keys() - outputs.keys():
            target = owned_path(out, rel)
            if target.is_file():
                produced[rel] = None
                target.unlink()  # Only files explicitly owned by the previous verified manifest.
        produced[MANIFEST] = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode('utf-8')
        from .state_io import save
        save(out / MANIFEST, data, sort_keys=True, newline='\n')
    return out
