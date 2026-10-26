"""절 단위 승인 장부: 본문 해시 기반 승인, 이월 유지, 범위 검토 관문."""

from sdd import approvals

import json
from pathlib import Path

import pytest


PAGE = "---\nsource_commit: " + "a" * 40 + "\nstatus: ok\n---\n\n# 개요\n\n본문 문장입니다.\n"


def test_승인은_본문이_같으면_유지되고_바뀌면_stale이_된다(tmp_cfg):
    ledger = approvals.load(tmp_cfg)
    assert approvals.page_status(ledger, "overview.md", PAGE) == "unreviewed"
    approvals.approve_page(ledger, "overview.md", PAGE, by="검토자", source_commit="a" * 40)
    assert approvals.page_status(ledger, "overview.md", PAGE) == "approved"
    # 이월은 frontmatter 의 기준 커밋만 바꾼다. 본문이 같으므로 승인이 유지된다.
    carried = PAGE.replace("a" * 40, "b" * 40)
    assert approvals.page_status(ledger, "overview.md", carried) == "approved"
    edited = PAGE.replace("본문 문장", "고친 문장")
    assert approvals.page_status(ledger, "overview.md", edited) == "stale"


def test_장부는_저장하고_다시_읽어도_같다(tmp_cfg):
    ledger = approvals.load(tmp_cfg)
    approvals.approve_page(ledger, "overview.md", PAGE, by="검토자")
    approvals.record_finding(ledger, "no-extracted-entity:file:meson.build", "accepted", by="검토자")
    approvals.save(tmp_cfg, ledger)
    loaded = approvals.load(tmp_cfg)
    assert approvals.page_status(loaded, "overview.md", PAGE) == "approved"
    assert loaded["findings"]["no-extracted-entity:file:meson.build"]["state"] == "accepted"


def test_save_preserves_sorted_format_schema_and_path_return(tmp_cfg):
    ledger = {"schema": 1, "pages": {"z.md": {"by": "검토자"}, "a.md": {}}, "findings": {}}
    path = approvals.save(tmp_cfg, ledger)
    assert path == approvals.ledger_path(tmp_cfg)
    expected = json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    assert path.read_bytes() == expected.encode("utf-8")
    assert approvals.load(tmp_cfg) == ledger


def test_save_failure_keeps_ledger_and_manuscript(tmp_cfg, monkeypatch):
    old = {"schema": 1, "pages": {}, "findings": {"kept": {"state": "deferred"}}}
    path = approvals.save(tmp_cfg, old)
    original = path.read_bytes()
    page = tmp_cfg.sdd_dir / "overview.md"
    page.write_text(PAGE, encoding="utf-8")
    manuscript = page.read_bytes()

    def fail(temporary, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        approvals.save(tmp_cfg, {"schema": 1, "pages": {"new.md": {}}, "findings": {}})
    assert path.read_bytes() == original
    assert page.read_bytes() == manuscript
    assert set(tmp_cfg.sdd_dir.iterdir()) == {path, page}


@pytest.mark.parametrize("kind", ["page", "finding"])
def test_accept_write_lock_precedes_load_and_readonly_listing_does_not_lock(
        tmp_cfg, monkeypatch, kind):
    from sdd.cli import main
    from sdd.locking import locked

    page = tmp_cfg.sdd_dir / "overview.md"
    page.parent.mkdir(parents=True)
    page.write_text(PAGE, encoding="utf-8")
    args = ["--config", str(tmp_cfg.root / "sdd.yaml"), "accept"]
    mutation = (["overview.md"] if kind == "page" else ["--finding", "reason:file:name"])
    mutation += ["--by", "검토자"]
    lock_path = approvals.ledger_path(tmp_cfg).with_suffix(".lock")
    load = approvals.load
    calls = []

    def tracked_load(cfg):
        calls.append(cfg)
        return load(cfg)

    monkeypatch.setattr(approvals, "load", tracked_load)
    with locked(lock_path):
        assert main(args + mutation) == 1
        assert calls == []
        assert not approvals.ledger_path(tmp_cfg).exists()
        assert main(args) == 0
        assert len(calls) == 1
    assert main(args + mutation) == 0
    assert page.read_text(encoding="utf-8") == PAGE


def test_accept_holds_same_lock_from_load_through_save_and_releases_on_failure(tmp_cfg, monkeypatch):
    from sdd.cli import main
    from sdd.locking import locked

    args = ["--config", str(tmp_cfg.root / "sdd.yaml"), "accept",
            "--finding", "reason:file:name", "--by", "검토자"]
    lock_path = approvals.ledger_path(tmp_cfg).with_suffix(".lock")
    load, save = approvals.load, approvals.save
    seen = []

    def assert_held():
        with pytest.raises(RuntimeError, match="이미 실행 중"):
            with locked(lock_path):
                pass

    def checked_load(cfg):
        assert_held()
        seen.append("load")
        return load(cfg)

    def checked_save(cfg, ledger):
        assert_held()
        seen.append("save")
        return save(cfg, ledger)

    monkeypatch.setattr(approvals, "load", checked_load)
    monkeypatch.setattr(approvals, "save", checked_save)
    assert main(args) == 0
    assert seen == ["load", "save"]

    def fail_save(cfg, ledger):
        assert_held()
        raise RuntimeError("failed save")

    monkeypatch.setattr(approvals, "save", fail_save)
    assert main(args) == 1
    with locked(lock_path):
        pass


def test_승인된_범위_항목만_관문에서_빠진다(tmp_cfg):
    coverage = {"findings": [
        {"reason": "no-extracted-entity", "kind": "file", "name": "meson.build", "files": ["meson.build"]},
        {"reason": "entity-outside-document-scope", "kind": "class", "name": "hal::New", "files": ["new.h"]},
    ]}
    ledger = approvals.load(tmp_cfg)
    assert len(approvals.open_findings(coverage, ledger)) == 2
    approvals.record_finding(ledger, "no-extracted-entity:file:meson.build", "accepted", by="검토자")
    remaining = approvals.open_findings(coverage, ledger)
    assert [f["name"] for f in remaining] == ["hal::New"]
    # 보류(deferred)는 확인만 한 상태이므로 관문을 통과시키지 않는다.
    approvals.record_finding(ledger, "entity-outside-document-scope:class:hal::New", "deferred", by="검토자")
    assert [f["name"] for f in approvals.open_findings(coverage, ledger)] == ["hal::New"]


def test_잘못된_상태는_기록을_거부한다(tmp_cfg):
    import pytest
    ledger = approvals.load(tmp_cfg)
    with pytest.raises(RuntimeError, match="accepted 또는 deferred"):
        approvals.record_finding(ledger, "k", "approved", by="검토자")


def test_accept_명령은_경로를_posix_로_정규화해_기록한다(tmp_cfg):
    from sdd.cli import main
    (tmp_cfg.sdd_dir / "scenarios").mkdir(parents=True)
    page = tmp_cfg.sdd_dir / "scenarios" / "flush.md"
    page.write_text(PAGE, encoding="utf-8")
    # Windows 식 백슬래시와 ./ 접두사가 섞여도 사이트·이월이 쓰는 키와 같아야 한다.
    assert main(["--config", str(tmp_cfg.root / "sdd.yaml"), "accept",
                 ".\\scenarios\\flush.md", "--by", "검토자"]) == 0
    ledger = approvals.load(tmp_cfg)
    assert list(ledger["pages"]) == ["scenarios/flush.md"]
    assert approvals.page_status(ledger, "scenarios/flush.md", PAGE) == "approved"


def test_검토_보고서가_장부_키와_상태를_보여준다():
    from sdd.impact import ImpactReport
    from sdd.impact_review import review_markdown

    report = ImpactReport(base="b" * 40, head="a" * 40, coverage={
        "status": "needs-review", "baseline_available": True, "ignored_files": [], "files": [],
        "entities": [], "findings": [
            {"reason": "no-extracted-entity", "kind": "file", "name": "meson.build", "files": ["meson.build"]}],
    })
    ledger = {"schema": 1, "pages": {}, "findings": {
        "no-extracted-entity:file:meson.build": {"state": "accepted", "by": "검토자", "at": "2026-09-25"}}}
    text = review_markdown(report, ledger)
    assert "no-extracted-entity:file:meson.build" in text
    assert "장부에서 승인됨" in text
    assert "sdd accept --finding" in text
