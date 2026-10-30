"""Reject incomplete libcamera facts before calling the document model."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
from pathlib import Path
import subprocess

from sdd.config import load
from sdd.facts.model import KnowledgeModel


def source_citations(cfg, model):
    """Keep material proof in its validated domain; structural locations stay Git-owned."""
    from sdd.product_context import record as material_record
    materials = {}
    for section in cfg.sections():
        for topic in section.get('design_topics', []):
            for selector in topic.get('sources', []):
                if selector.get('kind') == 'product':
                    materials[f"{section['id']}/{topic['id']}/{selector['id']}"] = selector
    source = copy.copy(model)
    source.evidence = {}
    for key, record in model.evidence.items():
        selector = materials.get(key)
        verified = selector is not None and record == material_record(selector, model.meta.get('source_commit'))
        if not verified:
            source.evidence[key] = record
    # A structural location with the same file:line must still pass the Git
    # check. Subtracting material citation strings would hide that collision.
    return source.citations()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = load(args.config.resolve())
    model = KnowledgeModel.load(cfg.facts_path)
    required = {"libcamera::Camera", "libcamera::CameraManager",
                "libcamera::Request", "libcamera::PipelineHandler"}
    missing = sorted(required - model.classes.keys())
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cfg.source_root, text=True
    ).strip()
    prefix = subprocess.check_output(['git', 'rev-parse', '--show-prefix'], cwd=cfg.source_root, text=True).strip()
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '--full-tree', '--name-only', head],
                                   cwd=cfg.source_root, text=True).splitlines()
    tracked = {name[len(prefix):] for name in tree if name.startswith(prefix)}
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                    cwd=cfg.source_root, text=True).splitlines()
    selected = {
        sec["id"]: sum(any(fnmatch.fnmatch(name, pattern)
                            or fnmatch.fnmatch(name.rsplit("::", 1)[-1], pattern)
                            for pattern in sec.get("facts", {}).get("classes", []))
                       for name in model.classes)
        for sec in cfg.sections() if sec.get("kind") == "prose" and sec.get('facts', {}).get('classes')
    }
    from sdd.generated_design import enabled, preflight
    evidence_errors = {}
    for section in cfg.sections():
        if enabled(section):
            try:
                preflight(model, section)
            except ValueError as exc:
                evidence_errors[section['id']] = str(exc)
    lengths: dict[str, int] = {}
    invalid = []
    citations = source_citations(cfg, model)
    for citation in sorted(citations):
        file, line = citation.rsplit(":", 1)
        if file not in lengths:
            path = cfg.source_root / file
            lengths[file] = len(path.read_text(encoding="utf-8", errors="replace").splitlines()) if path.is_file() else 0
        if file not in tracked or not 1 <= int(line) <= lengths[file]:
            invalid.append(citation)
    ok = (not missing and not dirty and bool(selected) and all(selected.values())
          and bool(lengths) and not invalid and not evidence_errors and model.meta.get("source_commit") == head)
    report = {
        "ok": ok, "source_commit": head, "classes": len(model.classes),
        "missing_required_classes": missing, "selected_classes": selected,
        "citations": len(model.citations()), "files": len(lengths),
        "product_material_citations": sorted(model.citations() - citations),
        "invalid_locations": invalid,
        "tracked_tree_files": len(tracked), "tracked_source_changes": dirty,
        "source_evidence_errors": evidence_errors,
        "source_only_sections": [sec['id'] for sec in cfg.sections() if enabled(sec) and not sec.get('facts', {}).get('classes')],
        "note": "Checks presence and locations; does not prove semantic completeness or prose accuracy.",
    }
    out = cfg.build_dir / "facts-verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
