import hashlib
import json

import pytest
import yaml

from sdd import evidence, idle_review, update
from sdd.facts.model import KnowledgeModel
from sdd.impact import ImpactReport
from test_automation import git, init, pipeline


@pytest.fixture
def idle_case(tmp_cfg):
    cfg = tmp_cfg
    init(cfg.source_root)
    text = "// BEGIN existing contract END\n// CANCEL_BEGIN pending requests are cancelled CANCEL_END\n"
    text += "class Camera { public: void cancel() {} void stop() { cancel(); } };\n"
    (cfg.source_root / "api.cpp").write_text(text)
    git(cfg.source_root, "add", ".")
    git(cfg.source_root, "commit", "-qm", "contracts")
    target = git(cfg.source_root, "rev-parse", "HEAD")
    section = {"id": "api", "kind": "prose", "title": "API 계약", "watch": ["api.cpp"],
        "next": {"title": "API 계약", "link": "api.md"},
        "design_requirements": [{"id": "existing", "question": "기존 계약은 무엇입니까?"}],
        "design_topics": [{"id": "existing", "title": "기존 계약", "question": "기존 계약은 무엇입니까?",
            "sources": [{"id": "src", "file": "api.cpp", "start": "BEGIN existing", "end": "END",
                         "sha256": hashlib.sha256(b"BEGIN existing contract END").hexdigest()}],
            "statements": [{"text": "기존 계약을 유지합니다.", "covers": ["existing"], "evidence": ["src"]}]}]}
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [section]}, allow_unicode=True), encoding="utf-8")
    cfg.scenarios_file.write_text("scenarios: []\n")
    cfg.raw["automation"] = {"idle_review": {"enabled": True}, "hermes": {"enabled": True}}
    model = KnowledgeModel(meta={"source_commit": target})
    evidence.collect(cfg, model)
    model.save(cfg.facts_path)
    update._default_generate(cfg, model, ImpactReport(target, target, sections={"api": ["baseline"]}))
    return cfg, target


def proposal():
    return {"kind": "add_topic", "section": "api", "reason": "취소 계약이 설명되지 않았습니다.",
        "requirement": {"id": "cancel", "question": "대기 중인 요청은 어떻게 종료됩니까?"},
        "topic": {"id": "cancel", "title": "요청 취소", "question": "대기 중인 요청은 어떻게 종료됩니까?",
            "sources": [{"id": "cancel", "file": "api.cpp", "start": "CANCEL_BEGIN", "end": "CANCEL_END"}],
            "statements": [{"text": "대기 중인 요청은 취소됩니다.", "evidence": ["cancel"], "covers": ["cancel"]}]}}


def test_idle_adds_one_topic_and_does_not_repeat(idle_case, monkeypatch):
    cfg, target = idle_case
    calls = []
    monkeypatch.setattr(idle_review, "_ask", lambda *a: (calls.append(1) or proposal()))
    assert idle_review.run(cfg, target, "job1")["status"] == "applied"
    assert len(cfg.sections()) == 1
    assert len(cfg.sections()[0]["design_topics"]) == 2
    assert "대기 중인 요청은 취소됩니다." in (cfg.sdd_dir / "api.md").read_text(encoding="utf-8")
    assert idle_review.run(cfg, target, "job1")["status"] == "applied"
    assert idle_review.run(cfg, target, "job2")["status"] == "exhausted"
    assert calls == [1]
    assert not (cfg.sdd_dir / "approvals.json").exists()


@pytest.mark.parametrize("failure", ["foreign_section", "bad_evidence", "approval", "invalid_json"])
def test_rejected_proposals_preserve_inputs(idle_case, monkeypatch, failure):
    cfg, target = idle_case
    before = idle_review._snapshot(cfg)
    data = proposal()
    if failure == "foreign_section":
        data["section"] = "new-category"
    elif failure == "bad_evidence":
        data["topic"]["sources"][0]["start"] = "invented"
    elif failure == "approval":
        cfg.raw["site"] = {"require_approval": True}
    else:
        data = "not JSON object"
    monkeypatch.setattr(idle_review, "_ask", lambda *a: data)
    assert idle_review.run(cfg, target, "job1")["status"] == "deferred"
    assert idle_review._snapshot(cfg) == before
    assert idle_review.run(cfg, target, "job2")["status"] == "exhausted"


def test_no_gap_never_rewrites_manuscripts(idle_case, monkeypatch):
    cfg, target = idle_case
    before = idle_review._snapshot(cfg)
    monkeypatch.setattr(idle_review, "_ask", lambda *a: {"kind": "no_gap", "reason": "이미 설명했습니다."})
    assert idle_review.run(cfg, target, "job")["status"] == "checked"
    assert idle_review._snapshot(cfg) == before


def test_concurrent_edit_is_not_overwritten(idle_case, monkeypatch):
    cfg, target = idle_case
    def ask(*args):
        (cfg.sdd_dir / "api.md").write_text("user edit", encoding="utf-8")
        return proposal()
    monkeypatch.setattr(idle_review, "_ask", ask)
    assert idle_review.run(cfg, target, "job")["status"] == "deferred"
    assert (cfg.sdd_dir / "api.md").read_text() == "user edit"
    assert len(cfg.sections()[0]["design_topics"]) == 1


def test_interrupted_promotion_resumes_same_candidate(idle_case, monkeypatch):
    cfg, target = idle_case
    monkeypatch.setattr(idle_review, "_ask", lambda *a: proposal())
    original = idle_review.shutil.copyfile
    def copy(src, dst, *args, **kwargs):
        if str(dst).endswith("scenarios.yaml.idle-tmp"):
            raise OSError("interrupted")
        return original(src, dst, *args, **kwargs)
    monkeypatch.setattr(idle_review.shutil, "copyfile", copy)
    with pytest.raises(OSError, match="interrupted"):
        idle_review.run(cfg, target, "job")
    cfg.raw["site"] = {"require_approval": True}
    with pytest.raises(RuntimeError, match="설정이 바뀌었"):
        idle_review.run(cfg, target, "job")
    cfg.raw.pop("site")
    monkeypatch.setattr(idle_review.shutil, "copyfile", original)
    monkeypatch.setattr(idle_review, "_ask", lambda *a: pytest.fail("must resume without model"))
    assert idle_review.run(cfg, target, "job")["status"] == "applied"
    assert len(cfg.sections()[0]["design_topics"]) == 2


def test_automation_only_reviews_when_initial_queue_is_empty(pipeline, monkeypatch):
    from sdd import automation
    cfg, repo, remote, calls = pipeline
    cfg.raw["automation"].update(idle_review={"enabled": True}, hermes={"enabled": True})
    target = git(cfg.source_root, "rev-parse", "HEAD")
    KnowledgeModel(meta={"source_commit": target}).save(cfg.facts_path)
    reviewed = []
    monkeypatch.setattr(idle_review, "run", lambda cfg, sha, job: (reviewed.append(sha) or {"status": "checked"}))
    assert automation.run(cfg) == 0
    assert reviewed == [target]
    (cfg.source_root / "new.cpp").write_text("new")
    git(cfg.source_root, "add", ".")
    git(cfg.source_root, "commit", "-qm", "new")
    assert automation.run(cfg) == 0
    assert reviewed == [target]


@pytest.mark.parametrize("entry, expected", [("Camera::stop()", "applied"), ("Camera::missing()", "deferred")])
def test_idle_scenario_uses_real_extraction(idle_case, monkeypatch, entry, expected):
    cfg, target = idle_case
    sections = cfg.sections()
    sections.append({"id": "flows", "kind": "per-scenario", "title": "호출 순서", "watch": ["api.cpp"],
                     "next": {"title": "API 계약", "link": "api.md"}})
    cfg.sections_file.write_text(yaml.safe_dump({"sections": sections}, allow_unicode=True), encoding="utf-8")
    cfg.raw["automation"]["idle_review"]["sections"] = ["flows"]
    cfg.compile_commands = cfg.root / "compile_commands.json"
    cfg.compile_commands.write_text(json.dumps([{"directory": str(cfg.source_root), "file": "api.cpp",
        "arguments": ["clang++", "-std=c++17", "-c", "api.cpp"]}]), encoding="utf-8")
    cfg.clang_uml_bin = "none"
    data = {"kind": "add_scenario", "section": "flows", "reason": "종료 호출을 추적합니다.",
            "scenario": {"id": "stop", "title": "캡처 종료", "from": entry}}
    monkeypatch.setattr(idle_review, "_ask", lambda *a: data)
    before = idle_review._snapshot(cfg)
    result = idle_review.run(cfg, target, "scenario")
    assert result["status"] == expected, result
    assert git(cfg.source_root, "rev-parse", "HEAD") == target
    if expected == "applied":
        assert "stop" in KnowledgeModel.load(cfg.facts_path).scenarios
        assert (cfg.sdd_dir / "scenarios" / "stop.md").is_file()
    else:
        assert idle_review._snapshot(cfg) == before


def test_smallest_window(idle_case, monkeypatch):
    cfg, target = idle_case
    cfg.raw["automation"]["idle_review"]["source_chars"] = 500
    data = proposal()
    data["topic"]["sources"][0]["start"] = "invented"
    monkeypatch.setattr(idle_review, "_ask", lambda *a: data)
    assert idle_review.run(cfg, target, "invalid")["status"] == "deferred"


def test_revision_retries_a_previously_deferred_proposal(idle_case, monkeypatch):
    cfg, target = idle_case
    monkeypatch.setattr(idle_review, "_ask", lambda *a: proposal())
    cfg.raw["site"] = {"require_approval": True}
    assert idle_review.run(cfg, target, "first")["status"] == "deferred"
    cfg.raw.pop("site")
    cfg.raw["automation"]["idle_review"]["revision"] = 2
    assert idle_review.run(cfg, target, "retry")["status"] == "applied"
