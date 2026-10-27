"""Reject incomplete libcamera facts before calling the document model."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import subprocess

from sdd.config import load
from sdd.facts.model import KnowledgeModel


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
    for citation in sorted(model.citations()):
        file, line = citation.rsplit(":", 1)
        if file not in lengths:
            path = cfg.source_root / file
            lengths[file] = len(path.read_text(encoding="utf-8", errors="replace").splitlines()) if path.is_file() else 0
        if not 1 <= int(line) <= lengths[file]:
            invalid.append(citation)
    ok = (not missing and bool(selected) and all(selected.values())
          and bool(lengths) and not invalid and not evidence_errors and model.meta.get("source_commit") == head)
    report = {
        "ok": ok, "source_commit": head, "classes": len(model.classes),
        "missing_required_classes": missing, "selected_classes": selected,
        "citations": len(model.citations()), "files": len(lengths),
        "invalid_locations": invalid,
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
