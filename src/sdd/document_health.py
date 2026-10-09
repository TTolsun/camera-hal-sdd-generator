"""Deterministic document lifecycle checks. Passing is never semantic approval.

The baseline is the last successful generation/build, not the last audit attempt.
Feature ownership and retirements are explicit, source-controlled configuration.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import PurePosixPath

from .config import section_output
from .export_html import _split
from .facts.model import KnowledgeModel


DEFAULTS = {"max_chars": 18000, "max_markdown_chars": 120000, "max_growth_ratio": 1.5,
            "min_growth_chars": 1000, "duplicate_min_chars": 180}


def settings(cfg):
    options = cfg.raw.get("documentation", {})
    if not isinstance(options, dict) or not isinstance(options.get("enabled", False), bool):
        raise ValueError("documentation.enabled must be a boolean")
    if set(options) - {"enabled", "limits", "pages", "features", "retired_pages"}:
        raise ValueError("Unknown documentation setting")
    if not isinstance(options.get("limits", {}), dict) or not isinstance(options.get("pages", {}), dict):
        raise ValueError("documentation limits/pages must be objects")
    limits = {**DEFAULTS, **options.get("limits", {})}
    _limits(limits)
    for key in ("features", "retired_pages"):
        if not isinstance(options.get(key, []), list):
            raise ValueError(f"documentation.{key} must be a list")
    for rel, overrides in options.get("pages", {}).items():
        page_path(cfg, rel)
        if not isinstance(overrides, dict):
            raise ValueError("Page limits must be an object")
        _limits({**limits, **overrides})
    return {**options, "limits": limits}


def _limits(values):
    if set(values) - set(DEFAULTS):
        raise ValueError("Unknown documentation limit")
    for name, value in values.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"documentation limit must be positive: {name}")
        if name != "max_growth_ratio" and not isinstance(value, int):
            raise ValueError(f"documentation limit must be an integer: {name}")
    if values["max_growth_ratio"] <= 1:
        raise ValueError("max_growth_ratio must exceed 1")


def page_path(cfg, rel):
    if not isinstance(rel, str) or not rel:
        raise ValueError("Document path must be a nonempty string")
    p = PurePosixPath(rel)
    target = (cfg.sdd_dir / rel).resolve()
    if (p.is_absolute() or ".." in p.parts or "\\" in rel or ":" in rel
            or p.suffix != ".md" or str(p) != rel
            or not target.is_relative_to(cfg.sdd_dir.resolve())):
        raise ValueError(f"Unsafe document path: {rel}")
    return target


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def paragraphs(text):
    """Measure prose, excluding generated tables, code, excerpts and metadata.

    Keep inline identifiers: two paragraphs about different symbols aren't duplicates.
    """
    _, body = _split(text)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", body)
    body = re.split(r'(?m)^(?:\?\?\? note "근거와 검토 정보"|## (?:근거와 검토 정보|다음 단계)\s*$)', body)[0]
    lines = ["" if re.match(r"\s*(?:#{1,6}\s|\||>|<|\[.*\]:|다음 단계:)", line) else line
             for line in body.splitlines()]
    return [re.sub(r"\s+", " ", block).strip() for block in
            re.split(r"\n\s*\n", "\n".join(lines)) if block.strip()]


def inventory(cfg):
    pages = {}
    for path in sorted(cfg.sdd_dir.rglob("*.md")):
        rel = path.relative_to(cfg.sdd_dir).as_posix()
        page_path(cfg, rel)
        text = path.read_text(encoding="utf-8")
        meta, _ = _split(text)
        blocks = paragraphs(text)
        pages[rel] = {"sha256": _hash(text), "chars": sum(map(len, blocks)),
                      "markdown_chars": len(text), "source_commit": str(meta.get("source_commit", "")),
                      "blocks": blocks, "method": meta.get("generation_method", "")}
    return pages


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def baseline(cfg):
    path = cfg.build_dir / "document-baseline.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("pages"), dict):
        raise ValueError("Unsupported document baseline")
    return data


def prepare(cfg):
    """Persist the pre-generation baseline once, so a failed retry cannot ratchet it."""
    if not settings(cfg).get("enabled"):
        return
    outputs = [section_output(s) for s in cfg.sections()]
    if len(outputs) != len(set(outputs)):
        raise ValueError("Multiple sections would overwrite the same document")
    for rel in outputs:
        page_path(cfg, rel)
    if baseline(cfg) is None:
        pages = inventory(cfg)
        if pages:
            _save(cfg.build_dir / "document-baseline.json", {"schema": 1, "pages": pages})


def retired_paths(cfg):
    if not settings(cfg).get("enabled"):
        return set()
    return {entry["path"] for entry in settings(cfg).get("retired_pages", [])}


def audit(cfg, model=None):
    options = settings(cfg)
    model = model or KnowledgeModel.load(cfg.facts_path)
    current = inventory(cfg)
    previous = (baseline(cfg) or {}).get("pages", {})
    sections = cfg.sections()
    expected = {}
    findings = []

    def finding(rule, pages, action, detail):
        findings.append({"rule": rule, "pages": sorted(set(pages)), "action": action, "detail": detail})

    for section in sections:
        rel = section_output(section)
        page_path(cfg, rel)
        if rel in expected:
            finding("duplicate-output", [rel], "merge", "Two sections own the same output path.")
        expected[rel] = section
    section_ids = [s["id"] for s in sections]
    if len(section_ids) != len(set(section_ids)):
        raise ValueError("Section ids must be unique for document ownership")
    if any(s.get("kind") == "per-scenario" for s in sections):
        for scenario in cfg.scenarios():
            rel = f"scenarios/{scenario['id']}.md"
            page_path(cfg, rel)
            if rel in expected:
                finding("duplicate-output", [rel], "merge", "Scenario and section output paths collide.")
            expected[rel] = {"kind": "scenario"}
            if scenario["id"] not in model.scenarios:
                finding("missing-scenario", [rel], "refresh", "Configured scenario was not extracted.")

    retired = set()
    for entry in options.get("retired_pages", []):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "reason", "replacements"}:
            raise ValueError("retired_pages requires path, sha256, reason, replacements")
        rel = entry["path"]
        page_path(cfg, rel)
        if rel in retired or rel in expected:
            raise ValueError(f"Retirement conflicts with active or repeated page: {rel}")
        if (not isinstance(entry["reason"], str) or not entry["reason"].strip()
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                or not isinstance(entry["replacements"], list)):
            raise ValueError(f"Invalid retirement: {rel}")
        for replacement in entry["replacements"]:
            page_path(cfg, replacement)
            if replacement not in expected or replacement not in current:
                finding("missing-replacement", [rel, replacement], "refresh", "Retirement replacement is not an active page.")
        old = current.get(rel) or previous.get(rel)
        if old and old["sha256"] != entry["sha256"]:
            finding("changed-retirement", [rel], "review", "Retired content changed; reconcile its unique information first.")
        retired.add(rel)

    for rel, section in expected.items():
        if rel not in current and section.get("kind") != "manual":
            finding("missing-page", [rel], "add", "Generate the configured page before publishing.")
    for rel in sorted((set(current) | set(previous)) - set(expected) - retired):
        finding("unowned-page", [rel], "retire-or-map", "Map the page to a section or declare a fingerprint-bound retirement.")

    blocks = defaultdict(list)
    active = {rel: page for rel, page in current.items() if rel not in retired}
    for rel, page in active.items():
        limits = {**options["limits"], **options.get("pages", {}).get(rel, {})}
        if page["chars"] > limits["max_chars"]:
            finding("page-too-long", [rel], "split", f"Prose has {page['chars']} characters; limit is {limits['max_chars']}.")
        if page["markdown_chars"] > limits["max_markdown_chars"]:
            finding("page-artifact-too-long", [rel], "split", "Markdown including tables and code exceeds its configured limit.")
        before = previous.get(rel, {}).get("chars", 0)
        if (before and page["chars"] - before >= limits["min_growth_chars"]
                and page["chars"] / before > limits["max_growth_ratio"]):
            finding("page-growth", [rel], "review-or-split", f"Prose grew from {before} to {page['chars']} characters.")
        if (rel in expected and expected[rel].get("kind") != "manual"
                and page["source_commit"] != model.meta.get("source_commit")):
            finding("stale-page", [rel], "refresh", "Page and facts source commits differ.")
        for block in page["blocks"]:
            if len(block) >= limits["duplicate_min_chars"]:
                blocks[block].append(rel)
    for block, locations in sorted(blocks.items()):
        if len(locations) > 1:
            finding("duplicate-prose", locations, "merge-or-link",
                    f"Repeated paragraph ({len(locations)} occurrences): {block[:120]}")

    ids = set()
    by_id = {s["id"]: s for s in sections}
    features = []
    for feature in options.get("features", []):
        if (not isinstance(feature, dict) or set(feature) - {"id", "primary", "sections", "scenarios", "symbols"}
                or not isinstance(feature.get("id"), str) or not feature["id"].strip()
                or feature["id"] in ids):
            raise ValueError("Feature must have a unique id and supported contract fields")
        ids.add(feature["id"])
        primary = feature.get("primary")
        page_path(cfg, primary)
        if primary not in expected or primary not in active:
            finding("feature-primary", [primary], "add-or-map", f"Feature {feature['id']} needs one active primary document.")
        for field in ("sections", "scenarios", "symbols"):
            values = feature.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError(f"Feature {field} must be a string list")
            for value in values:
                if field == "sections":
                    present = value in by_id and section_output(by_id[value]) in active
                elif field == "scenarios":
                    present = (value in model.scenarios and f"scenarios/{value}.md" in expected
                               and f"scenarios/{value}.md" in active)
                else:
                    present = value in model.classes or value in model.functions
                if not present:
                    finding("feature-contract", [primary], "refresh-or-retire",
                            f"Feature {feature['id']} is missing {field}: {value}")
        features.append({"id": feature["id"], "primary": primary})

    report = {"schema": 1, "source_commit": model.meta.get("source_commit"),
              "status": "needs-review" if findings else "ok", "human_review": "not-performed",
              "pages": {rel: {k: v for k, v in page.items() if k not in {"blocks", "method"}}
                        for rel, page in active.items()},
              "features": features, "retired_pages": sorted(retired), "findings": findings,
              "limitations": ["Exact prose repetition only; no semantic equivalence or contradiction detection.",
                              "Feature contracts are configured, not inferred from arbitrary code changes.",
                              "Split/merge/retirement decisions require preserving unique source-backed content."]}
    _save(cfg.build_dir / "document-health.json", report)
    lines = ["# 문서 수명주기 검사", "", f"상태: {report['status']} · 활성 원고 {len(active)}개", "",
             "자동 검사는 사람의 의미 승인이나 실기기 검증이 아닙니다.", ""]
    for item in findings:
        lines.append(f"- {item['rule']}: {', '.join(item['pages'])} → {item['action']}. {item['detail']}")
    if not findings:
        lines.append("설정한 분량·중복·범위 검사에서 문제를 발견하지 못했습니다.")
    (cfg.build_dir / "document-health.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def enforce(cfg, model=None):
    if not settings(cfg).get("enabled"):
        return None
    report = audit(cfg, model)
    if report["findings"]:
        raise RuntimeError(f"Document lifecycle checks failed ({len(report['findings'])}); "
                           f"see {cfg.build_dir / 'document-health.md'}")
    return report


def checkpoint(cfg, report):
    if report is not None:
        _save(cfg.build_dir / "document-baseline.json", {"schema": 1, "pages": report["pages"]})
