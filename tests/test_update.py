"""증분 자동 갱신: 순서 보장, 실패 후 재개, 사람 리뷰 관문."""

import subprocess

import pytest

from sdd import approvals, update
from sdd.facts.model import KnowledgeModel
from sdd.source_git import resolve_commit


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def source_repo(tmp_cfg):
    repo = tmp_cfg.source_root
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "테스트")
    shas = []
    for i in range(4):
        (repo / "a.txt").write_text(f"내용 {i}\n", encoding="utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", f"c{i}")
        shas.append(resolve_commit(repo, "HEAD"))
    return shas


def _steps(order: list[str]):
    def fake_extract(cfg):
        sha = resolve_commit(cfg.source_root, "HEAD")
        model = KnowledgeModel(meta={"source_commit": sha})
        model.save(cfg.facts_path)
        order.append(sha)
        return model

    return update.Steps(prepare_compdb=lambda cfg, sha: None, extract=fake_extract,
                        generate=lambda cfg, model, report: None)


def _seed_baseline(cfg, sha):
    KnowledgeModel(meta={"source_commit": sha}).save(cfg.facts_path)


def test_document_health_failure_retries_same_commit_without_advancing_baseline(tmp_cfg, source_repo):
    import yaml
    from sdd import document_health
    _seed_baseline(tmp_cfg, source_repo[0])
    tmp_cfg.raw["documentation"] = {"enabled": True}
    tmp_cfg.sections_file.write_text(yaml.safe_dump({"sections": [
        {"id": "overview", "kind": "prose", "output": "overview.md"}]}))
    tmp_cfg.sdd_dir.mkdir()
    page = tmp_cfg.sdd_dir / "overview.md"
    page.write_text(f"---\nsource_commit: {source_repo[0]}\n---\n\n" + "short " * 180)
    ledger = approvals.load(tmp_cfg)
    approvals.record_finding(ledger, "no-extracted-entity:file:a.txt", "accepted", by="reviewer")
    approvals.save(tmp_cfg, ledger)
    order = []
    steps = _steps(order)
    def generate(cfg, model, report):
        page.write_text(f"---\nsource_commit: {model.meta['source_commit']}\n---\n\n" + "growth " * 1000)
    steps.generate = generate
    first = update.run_update(tmp_cfg, to=source_repo[1], steps=steps, log=lambda _: None)
    assert first.exit_code == 1
    before = document_health.baseline(tmp_cfg)
    again = update.run_update(tmp_cfg, to=source_repo[1], steps=steps, log=lambda _: None)
    assert again.exit_code == 1 and again.processed == []
    assert order == [source_repo[1], source_repo[1]]
    assert document_health.baseline(tmp_cfg) == before
    assert update.load_state(tmp_cfg)["last_done"] == ""


def test_승인되지_않은_범위_항목은_생성_전에_멈춘다(tmp_cfg, source_repo):
    _seed_baseline(tmp_cfg, source_repo[0])
    result = update.run_update(tmp_cfg, steps=_steps([]), log=lambda _: None)
    assert result.exit_code == 2
    assert result.processed == []
    assert update.load_state(tmp_cfg)["last_done"] == ""     # 실패한 커밋을 완료로 적지 않는다
    assert (tmp_cfg.build_dir / "impact-review.md").exists()


def test_장부_승인_후_커밋을_오래된_것부터_차례로_처리한다(tmp_cfg, source_repo):
    _seed_baseline(tmp_cfg, source_repo[0])
    ledger = approvals.load(tmp_cfg)
    approvals.record_finding(ledger, "no-extracted-entity:file:a.txt", "accepted", by="검토자")
    approvals.save(tmp_cfg, ledger)
    order: list[str] = []
    result = update.run_update(tmp_cfg, steps=_steps(order), log=lambda _: None)
    assert result.exit_code == 0
    assert order == source_repo[1:]                          # 오래된 커밋부터, 건너뛰지 않고
    assert update.load_state(tmp_cfg)["last_done"] == source_repo[-1]
    # 소비한 기준 facts 사본은 정리해서 장기 운영에서 쌓이지 않게 한다.
    assert list(tmp_cfg.build_dir.glob("facts-*.json")) == []
    # 재실행은 새 커밋이 없으므로 아무것도 하지 않는다.
    again = update.run_update(tmp_cfg, steps=_steps(order), log=lambda _: None)
    assert again.processed == [] and order == source_repo[1:]


def test_실패한_커밋은_기록되고_다음_실행이_같은_커밋부터_재시도한다(tmp_cfg, source_repo):
    _seed_baseline(tmp_cfg, source_repo[0])
    ledger = approvals.load(tmp_cfg)
    approvals.record_finding(ledger, "no-extracted-entity:file:a.txt", "accepted", by="검토자")
    approvals.save(tmp_cfg, ledger)
    calls = {"n": 0}
    order: list[str] = []
    good = _steps(order)

    def failing_extract(cfg):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("파싱 실패")
        return good.extract(cfg)

    steps = update.Steps(prepare_compdb=lambda cfg, sha: None, extract=failing_extract,
                         generate=lambda cfg, model, report: None)
    result = update.run_update(tmp_cfg, steps=steps, log=lambda _: None)
    assert result.exit_code == 1
    state = update.load_state(tmp_cfg)
    assert state["last_done"] == source_repo[1]              # 성공한 곳까지만
    assert source_repo[2] in state["failed"]
    # 재시도: 같은 커밋부터 이어서 끝까지 처리하고 실패 기록을 지운다.
    result = update.run_update(tmp_cfg, steps=steps, log=lambda _: None)
    assert result.exit_code == 0
    state = update.load_state(tmp_cfg)
    assert state["last_done"] == source_repo[-1]
    assert state["failed"] == {}
    assert order == source_repo[1:]


def test_소스에_커밋되지_않은_변경이_있으면_시작하지_않는다(tmp_cfg, source_repo):
    (tmp_cfg.source_root / "a.txt").write_text("작업 중\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="커밋되지 않은 변경"):
        update.run_update(tmp_cfg, steps=_steps([]), log=lambda _: None)


def test_생성_결과가_needs_review_이면_다음_커밋으로_가지_않는다(tmp_cfg, source_repo):
    _seed_baseline(tmp_cfg, source_repo[0])
    ledger = approvals.load(tmp_cfg)
    approvals.record_finding(ledger, "no-extracted-entity:file:a.txt", "accepted", by="검토자")
    approvals.save(tmp_cfg, ledger)
    order: list[str] = []
    base = _steps(order)

    def generate_needs_review(cfg, model, report):
        tmp_cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
        (tmp_cfg.sdd_dir / "overview.md").write_text(
            "---\nstatus: needs-review\n---\n\n# 개요\n", encoding="utf-8")

    steps = update.Steps(prepare_compdb=lambda cfg, sha: None, extract=base.extract,
                         generate=generate_needs_review)
    result = update.run_update(tmp_cfg, steps=steps, log=lambda _: None)
    assert result.exit_code == 3
    assert result.processed == [source_repo[1]]              # 생성까지 마친 커밋은 완료로 남긴다
    assert update.load_state(tmp_cfg)["last_done"] == source_repo[1]
    assert "needs-review" in result.stopped_reason
    # 검토 없이 재실행하면 시작 관문이 막는다. 커밋을 더 처리하지 않는다.
    again = update.run_update(tmp_cfg, steps=steps, log=lambda _: None)
    assert again.exit_code == 3 and again.processed == []
    assert update.load_state(tmp_cfg)["last_done"] == source_repo[1]
    # 사람이 검토하고 승인을 기록하면 관문이 열린다.
    page = tmp_cfg.sdd_dir / "overview.md"
    approvals.approve_page(ledger, "overview.md", page.read_text(encoding="utf-8"), by="검토자")
    approvals.save(tmp_cfg, ledger)
    # 재생성된 본문이 승인 시점과 같으므로 승인이 유지되어 남은 커밋을 끝까지 처리한다.
    resumed = update.run_update(tmp_cfg, steps=steps, log=lambda _: None)
    assert resumed.processed == source_repo[2:]
    assert update.load_state(tmp_cfg)["last_done"] == source_repo[-1]


def test_기준이_이력에서_사라지면_전체_재처리_대신_중단한다(tmp_cfg, source_repo):
    _seed_baseline(tmp_cfg, source_repo[0])
    update.save_state(tmp_cfg, {"schema": 1, "last_done": "f" * 40, "failed": {}})
    with pytest.raises(RuntimeError, match="조상이 아닙니다"):
        update.run_update(tmp_cfg, steps=_steps([]), log=lambda _: None)
