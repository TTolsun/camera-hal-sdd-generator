import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from sdd.hermes_review import revise
from sdd.facts.model import KnowledgeModel
from sdd.impact import ImpactReport


@pytest.fixture
def review_case(tmp_cfg, monkeypatch):
    repo = tmp_cfg.source_root
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, encoding="utf-8").strip()
    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    old, new = "BEGIN old contract END", "BEGIN new contract END"
    (repo / "api.cpp").write_text(old)
    git("add", ".")
    git("commit", "-qm", "old")
    base = git("rev-parse", "HEAD")
    (repo / "api.cpp").write_text(new)
    git("commit", "-qam", "new")
    head = git("rev-parse", "HEAD")
    sections = {"sections": [{"id": "api", "kind": "prose", "title": "API",
        "design_requirements": [{"id": "contract", "question": "What changed?"}],
        "design_topics": [{"id": "contract", "question": "What changed?", "title": "Contract",
            "sources": [{"id": "api", "file": "api.cpp", "start": "BEGIN", "end": "END",
                         "sha256": hashlib.sha256(old.encode()).hexdigest()}],
            "statements": [{"text": "기존 계약입니다.", "covers": ["contract"], "evidence": ["api"]}]}]}]}
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding="utf-8")
    model = KnowledgeModel(meta={"source_commit": head})
    report = ImpactReport(base, head, changed_files=["api.cpp"])
    return tmp_cfg, model, report


def reply(monkeypatch, value):
    original = subprocess.run
    def run(args, **kwargs):
        if args[0] == "fake-hermes":
            return SimpleNamespace(stdout=json.dumps(value, ensure_ascii=False))
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, "run", run)


def test_changes_only_reviewed_statements_and_hashes(review_case, monkeypatch):
    cfg, model, report = review_case
    reply(monkeypatch, {"reason": "소스의 계약이 변경됐습니다.", "statements": [
        {"text": "새 계약입니다.", "covers": ["contract"], "evidence": ["api"]}]})
    revise(cfg, model, report, {"command": ["fake-hermes", "{prompt}"]})
    topic = cfg.sections()[0]["design_topics"][0]
    assert topic["statements"][0]["text"] == "새 계약입니다."
    assert topic["sources"][0]["sha256"] == hashlib.sha256(b"BEGIN new contract END").hexdigest()
    assert "api" in report.sections
    assert not (cfg.sdd_dir / "approvals.json").exists()
    retry = ImpactReport(report.base, report.head, changed_files=["api.cpp"])
    revise(cfg, model, retry, {"command": ["must-not-call-again", "{prompt}"]})
    assert "api" in retry.sections


@pytest.mark.parametrize("response", [
    {"needs_review": "insufficient evidence"},
    {"reason": "x", "statements": []},
    {"reason": "x", "statements": [{"text": "x", "evidence": ["invented"], "covers": ["contract"]}]},
    {"reason": "x", "statements": [{"text": "x", "evidence": ["api"], "covers": ["contract"], "kind": "limitation"}]},
])
def test_bad_proposal_preserves_configuration(review_case, monkeypatch, response):
    cfg, model, report = review_case
    original = cfg.sections_file.read_bytes()
    reply(monkeypatch, response)
    with pytest.raises((ValueError, RuntimeError)):
        revise(cfg, model, report, {"command": ["fake-hermes", "{prompt}"]})
    assert cfg.sections_file.read_bytes() == original


def test_missing_anchor_and_budget_do_not_call_hermes(review_case, monkeypatch):
    cfg, model, report = review_case
    original = cfg.sections_file.read_bytes()
    with pytest.raises(RuntimeError, match="입력 한도"):
        revise(cfg, model, report, {"command": ["must-not-run", "{prompt}"], "max_input_chars": 1})
    assert cfg.sections_file.read_bytes() == original
    cfg.sections_file.write_text(original.decode().replace("start: BEGIN", "start: MISSING"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="앵커"):
        revise(cfg, model, report, {})


def test_concurrent_edit_during_hermes_call_is_preserved(review_case, monkeypatch):
    cfg, model, report = review_case
    original_run = subprocess.run
    edited = cfg.sections_file.read_text(encoding="utf-8").replace("title: API", "title: User edit")
    def run(args, **kwargs):
        if args[0] == "fake-hermes":
            cfg.sections_file.write_text(edited, encoding="utf-8")
            return SimpleNamespace(stdout=json.dumps({"reason": "reviewed", "statements": [
                {"text": "새 계약입니다.", "covers": ["contract"], "evidence": ["api"]}]}))
        return original_run(args, **kwargs)
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="검토 중 sections 설정이 변경"):
        revise(cfg, model, report, {"command": ["fake-hermes", "{prompt}"]})
    assert cfg.sections_file.read_text(encoding="utf-8") == edited
