import json

import pytest
import yaml

from sdd import document_health as health
from sdd.export_site import export_site


def setup(cfg, model, names=("overview",)):
    cfg.raw["documentation"] = {"enabled": True}
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [
        {"id": name, "title": name, "kind": "prose", "output": f"{name}.md"} for name in names]}))
    cfg.scenarios_file.write_text("scenarios: []\n")
    model.save(cfg.facts_path)
    cfg.sdd_dir.mkdir(parents=True, exist_ok=True)


def page(cfg, rel="overview.md", body="A source-bound explanation.", commit="abc123"):
    path = cfg.sdd_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nsource_commit: {commit}\ngeneration_method: deterministic\nstatus: ok\n---\n\n# Guide\n\n{body}\n", encoding="utf-8")
    return path


def rules(report):
    return {f["rule"] for f in report["findings"]}


def test_failed_retries_cannot_ratchet_growth_baseline(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model)
    page(tmp_cfg, body="small prose " * 80)
    health.prepare(tmp_cfg)
    original = health.baseline(tmp_cfg)
    page(tmp_cfg, body="expanded prose " * 220)
    for _ in range(2):
        health.prepare(tmp_cfg)
        with pytest.raises(RuntimeError, match="lifecycle"):
            health.enforce(tmp_cfg)
        assert health.baseline(tmp_cfg) == original
    assert "page-growth" in rules(health.audit(tmp_cfg))
    page(tmp_cfg, body="corrected prose " * 70)
    report = health.enforce(tmp_cfg)
    health.checkpoint(tmp_cfg, report)
    assert health.baseline(tmp_cfg) != original


def test_new_feature_adds_page_without_commit_count_penalty(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model)
    page(tmp_cfg)
    health.prepare(tmp_cfg)
    setup(tmp_cfg, sample_model, ("overview", "hdr"))
    page(tmp_cfg, "hdr.md", "HDR processing conditions.")
    tmp_cfg.raw["documentation"]["features"] = [
        {"id": "hdr", "primary": "hdr.md", "sections": ["hdr"], "symbols": ["CameraDevice"]}]
    first = health.audit(tmp_cfg)
    assert first["status"] == "ok"
    assert first == health.audit(tmp_cfg)
    assert len(first["pages"]) == 2
    assert first["human_review"] == "not-performed"


def test_duplicate_prose_but_not_tables_or_evidence(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model, ("overview", "other"))
    prose = "Unique technical explanation is needed. " * 8
    for rel in ("overview.md", "other.md"):
        page(tmp_cfg, rel, prose + '\n\n```cpp\ncode\n```\n\n| same | table |\n\n??? note "근거와 검토 정보"\n    evidence')
    assert "duplicate-prose" in rules(health.audit(tmp_cfg))
    page(tmp_cfg, "other.md", "Another explanation.\n\n| same | table |\n\n```cpp\n" + prose + "\n```")
    assert health.audit(tmp_cfg)["status"] == "ok"


def test_same_page_repetition_and_table_size(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model)
    block = "Repeated technical paragraph. " * 8
    page(tmp_cfg, body=block + "\n\n" + block)
    assert "duplicate-prose" in rules(health.audit(tmp_cfg))
    page(tmp_cfg, body="| column |\n" * 100)
    tmp_cfg.raw["documentation"]["limits"] = {"max_markdown_chars": 500}
    assert "page-artifact-too-long" in rules(health.audit(tmp_cfg))


def test_missing_deleted_and_stale_contracts(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model, ("overview", "detail"))
    page(tmp_cfg, commit="old")
    tmp_cfg.raw["documentation"]["features"] = [
        {"id": "capture", "primary": "overview.md", "sections": ["detail"],
         "symbols": ["DeletedClass"], "scenarios": ["missing"]}]
    assert {"missing-page", "stale-page", "feature-contract"} <= rules(health.audit(tmp_cfg))


def test_retirement_requires_unchanged_content_and_active_replacement(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model)
    page(tmp_cfg)
    old = page(tmp_cfg, "old.md", "Preserve unique content before retirement.")
    health.prepare(tmp_cfg)
    assert "unowned-page" in rules(health.audit(tmp_cfg))
    tmp_cfg.raw["documentation"]["retired_pages"] = [{
        "path": "old.md", "sha256": health.inventory(tmp_cfg)["old.md"]["sha256"],
        "reason": "The current overview contains the reviewed content.", "replacements": ["overview.md"]}]
    assert health.audit(tmp_cfg)["status"] == "ok"
    assert old.exists()  # Audit never deletes manuscript content.
    old.write_text("New unique content")
    assert "changed-retirement" in rules(health.audit(tmp_cfg))


def test_unexpected_deleted_page_does_not_disappear_silently(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model, ("overview", "old"))
    page(tmp_cfg)
    page(tmp_cfg, "old.md")
    health.prepare(tmp_cfg)
    setup(tmp_cfg, sample_model)
    (tmp_cfg.sdd_dir / "old.md").unlink()
    assert "unowned-page" in rules(health.audit(tmp_cfg))


@pytest.mark.parametrize("rel", ["../outside.md", "C:/outside.md", "scenarios/../../outside.md", "./x.md", "x\\y.md"])
def test_unsafe_paths_fail_before_read(tmp_cfg, sample_model, rel):
    setup(tmp_cfg, sample_model)
    tmp_cfg.raw["documentation"]["features"] = [{"id": "bad", "primary": rel}]
    with pytest.raises(ValueError, match="path"):
        health.audit(tmp_cfg)


@pytest.mark.parametrize("value", [0, -1, True, "100", float("nan"), float("inf")])
def test_invalid_limits_fail_closed(tmp_cfg, value):
    tmp_cfg.raw["documentation"] = {"enabled": True, "limits": {"max_chars": value}}
    with pytest.raises(ValueError):
        health.settings(tmp_cfg)


def test_site_failure_preserves_published_files_and_baseline(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model)
    page(tmp_cfg)
    health.prepare(tmp_cfg)
    before = health.baseline(tmp_cfg)
    out = export_site(tmp_cfg)
    files = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    page(tmp_cfg, body="overgrown " * 2200)
    with pytest.raises(RuntimeError, match="lifecycle"):
        export_site(tmp_cfg)
    assert files == {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert health.baseline(tmp_cfg) == before


def test_retired_scenario_is_removed_from_site_but_manuscript_preserved(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model, ("overview", "scenarios/old"))
    page(tmp_cfg)
    old = page(tmp_cfg, "scenarios/old.md")
    out = export_site(tmp_cfg)
    assert (out / "scenarios/old.html").exists()
    setup(tmp_cfg, sample_model)
    tmp_cfg.raw["documentation"]["retired_pages"] = [{
        "path": "scenarios/old.md", "sha256": health.inventory(tmp_cfg)["scenarios/old.md"]["sha256"],
        "reason": "Replaced with the overview.", "replacements": ["overview.md"]}]
    out = export_site(tmp_cfg)
    assert not (out / "scenarios/old.html").exists()
    assert old.exists()


def test_cli_audit_is_read_only_for_baseline_and_returns_failure(tmp_cfg, sample_model):
    from sdd.cli import main
    setup(tmp_cfg, sample_model)
    page(tmp_cfg, body="too much prose " * 2000)
    # The CLI loads its own config; audits run even when automatic checks are disabled.
    assert main(["--config", str(tmp_cfg.root / "sdd.yaml"), "audit-docs"]) == 2
    assert health.baseline(tmp_cfg) is None


def test_output_collision_rejected_before_generation(tmp_cfg, sample_model):
    setup(tmp_cfg, sample_model, ("overview", "overview"))
    original = page(tmp_cfg).read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        health.prepare(tmp_cfg)
    assert (tmp_cfg.sdd_dir / "overview.md").read_bytes() == original
