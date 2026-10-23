"""범위 검토 항목의 자동 분류(주석·공백·#include)와 LLM 판정(승인과 별도 기록)."""

import json
import subprocess

import pytest
import yaml

from sdd import approvals, coverage_triage, update
from sdd.change_kind import NON_SEMANTIC, classify
from sdd.facts.model import ClassInfo, KnowledgeModel, Location
from sdd.impact import compute
from sdd.impact_review import review_markdown
from sdd.llm import AgentError
from sdd.source_git import resolve_commit

HEADER = """#pragma once
#include <vector>

/* Device keeps frames. */
class Dev {
public:
    int run(const char *path = "a//b"); // run once
    int *ptr;
};
"""


@pytest.mark.parametrize("new", [
    HEADER.replace("#include <vector>", "#include <vector>\n#include <array>"),
    HEADER.replace("/* Device keeps frames. */", "/**\n * Device keeps every frame.\n */"),
    HEADER.replace("int run(const char *path = \"a//b\"); // run once",
                   "int run(const char *path = \"a//b\");\n    // run once, then stop"),
    HEADER.replace("    int *ptr;", "        int *ptr;\n\n"),
])
def test_주석_공백_include_만_바뀌면_의미_없는_변경이다(new):
    assert classify("dev.h", HEADER, new) == NON_SEMANTIC


@pytest.mark.parametrize("new", [
    HEADER.replace("int *ptr;", "int *ptr = nullptr;"),
    HEADER.replace('"a//b"', '"a//c"'),                       # 문자열 안의 // 는 주석이 아니다
    HEADER.replace("#pragma once", "#pragma once\n#define DEV_BIG 1"),
    HEADER.replace("public:", "protected:"),
])
def test_코드가_바뀌면_분류하지_않는다(new):
    assert classify("dev.h", HEADER, new) is None


def test_추가_삭제된_파일과_C_계열이_아닌_파일은_분류하지_않는다():
    assert classify("dev.h", None, HEADER) is None
    assert classify("dev.h", HEADER, None) is None
    assert classify("Android.mk", "# a\nX := 1\n", "# b\nX := 1\n") is None


def _sections(cfg, values):
    cfg.sections_file.write_text(yaml.safe_dump({"sections": values}), encoding="utf-8")


def test_의미_없는_변경_파일에만_걸린_항목은_검토_항목이_아니다(tmp_cfg):
    _sections(tmp_cfg, [{"id": "api", "facts": {"classes": ["Other"]}}])
    model = KnowledgeModel(classes={"Dev": ClassInfo("Dev", Location("dev.h", 5)),
                                    "Both": ClassInfo("Both", Location("both.h", 3))})
    model.classes["Both"].methods = []
    files = ["dev.h", "both.h", "rpi.h"]
    report = compute(tmp_cfg, model, files, "a", "b", non_semantic={"dev.h": NON_SEMANTIC, "rpi.h": NON_SEMANTIC})
    assert [f["name"] for f in report.coverage["findings"]] == ["Both"]
    assert {c["name"] for c in report.coverage["classified"]} == {"Dev", "rpi.h"}
    assert {f["file"]: f["status"] for f in report.coverage["files"]}["rpi.h"] == "non-semantic"
    text = review_markdown(report)
    assert "## 자동 분류한 변경" in text and "`Dev`" in text and "사람의 승인이 아니며" in text


def test_한_항목이_의미_있는_변경_파일에도_걸리면_검토_항목으로_남는다(tmp_cfg):
    _sections(tmp_cfg, [])
    model = KnowledgeModel(classes={"Dev": ClassInfo("Dev", Location("dev.h", 5))})
    from sdd.facts.model import Method
    model.classes["Dev"].methods = [Method("run", Location("dev.h", 6), def_loc=Location("dev.cpp", 9))]
    report = compute(tmp_cfg, model, ["dev.h", "dev.cpp"], "a", "b", non_semantic={"dev.h": NON_SEMANTIC})
    assert [f["name"] for f in report.coverage["findings"]] == ["Dev"]
    assert report.coverage["classified"] == []


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def header_repo(tmp_cfg):
    """c0: 헤더 작성, c1: #include 한 줄 추가, c2: 멤버 변경."""
    repo = tmp_cfg.source_root
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    shas = []
    for text in (HEADER, HEADER.replace("#include <vector>", "#include <vector>\n#include <array>"),
                 HEADER.replace("int *ptr;", "long *ptr;").replace("#include <vector>", "#include <vector>\n#include <array>")):
        (repo / "dev.h").write_text(text, encoding="utf-8")
        _git(repo, "add", "dev.h")
        _git(repo, "commit", "-q", "-m", "c")
        shas.append(resolve_commit(repo, "HEAD"))
    _sections(tmp_cfg, [{"id": "api", "facts": {"classes": ["Other"]}}])
    return shas


def test_compute_가_소스_저장소의_두_판을_읽어_분류한다(tmp_cfg, header_repo):
    model = KnowledgeModel(classes={"Dev": ClassInfo("Dev", Location("dev.h", 5))})
    include_only = compute(tmp_cfg, model, ["dev.h"], header_repo[0], header_repo[1])
    assert include_only.coverage["findings"] == [] and include_only.coverage["status"] == "mapped"
    code = compute(tmp_cfg, model, ["dev.h"], header_repo[1], header_repo[2])
    assert [f["name"] for f in code.coverage["findings"]] == ["Dev"]


class FakeAgent:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, system, user, tag="prompt"):
        self.calls.append(user)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _report(tmp_cfg, header_repo):
    model = KnowledgeModel(classes={"Dev": ClassInfo("Dev", Location("dev.h", 5))})
    return compute(tmp_cfg, model, ["dev.h"], header_repo[1], header_repo[2])


def _enable(cfg, **opts):
    cfg.raw.setdefault("review", {})["coverage_triage"] = {"enabled": True, "agent": {"kind": "ollama"}, **opts}


def test_LLM_판정은_승인_장부가_아니라_별도_기록에_남는다(tmp_cfg, header_repo):
    _enable(tmp_cfg)
    report = _report(tmp_cfg, header_repo)
    agent = FakeAgent(['```json\n{"decision": "out-of-scope", "reason": "포인터 타입만 바뀐 내부 클래스입니다."}\n```'])
    judged = coverage_triage.triage(tmp_cfg, report, approvals.load(tmp_cfg), agent=agent)
    key = "entity-outside-document-scope:class:Dev"
    assert judged[key]["decision"] == "out-of-scope" and judged[key]["head"] == header_repo[2]
    assert "long *ptr" in json.loads(agent.calls[0].split("\n\nDocument catalog:")[0])["diff"]
    assert not approvals.ledger_path(tmp_cfg).exists()          # 사람 승인 장부는 건드리지 않는다
    assert coverage_triage.load(tmp_cfg)["entries"][key]["reason"].startswith("포인터")
    # pass_gate 가 꺼져 있으면 판정이 있어도 관문은 그대로다.
    assert coverage_triage.passed(tmp_cfg, judged) == set()
    assert approvals.open_findings(report.coverage, {}, coverage_triage.passed(tmp_cfg, judged))
    _enable(tmp_cfg, pass_gate=True)
    assert approvals.open_findings(report.coverage, {}, coverage_triage.passed(tmp_cfg, judged)) == []
    text = review_markdown(report, {}, judged, {key})
    assert "LLM 판정: **범위 밖**" in text and "사람 검토 전 · 관문 제외" in text


def test_같은_비교_범위는_다시_묻지_않고_범위가_바뀌면_다시_묻는다(tmp_cfg, header_repo):
    _enable(tmp_cfg)
    report = _report(tmp_cfg, header_repo)
    agent = FakeAgent(['{"decision": "needs-document", "reason": "공개 동작이 바뀝니다."}'])
    coverage_triage.triage(tmp_cfg, report, {}, agent=agent)
    coverage_triage.triage(tmp_cfg, report, {}, agent=agent)
    assert len(agent.calls) == 1
    report.base = header_repo[0]
    agent.answers.append('{"decision": "unsure", "reason": "근거가 부족합니다."}')
    assert coverage_triage.triage(tmp_cfg, report, {}, agent=agent)[
        "entity-outside-document-scope:class:Dev"]["decision"] == "unsure"


@pytest.mark.parametrize("answer", ["범위 밖입니다.", '{"decision": "approve", "reason": "x"}',
                                    '{"decision": "out-of-scope", "reason": ""}', AgentError("timeout")])
def test_형식이_어긋나거나_호출이_실패하면_판단_불가로_남는다(tmp_cfg, header_repo, answer):
    _enable(tmp_cfg, pass_gate=True)
    judged = coverage_triage.triage(tmp_cfg, _report(tmp_cfg, header_repo), {}, agent=FakeAgent([answer]))
    assert [e["decision"] for e in judged.values()] == ["unsure"]
    assert coverage_triage.passed(tmp_cfg, judged) == set()


def test_사람이_승인한_항목과_dry_run_은_모델을_부르지_않는다(tmp_cfg, header_repo):
    report = _report(tmp_cfg, header_repo)
    ledger = approvals.load(tmp_cfg)
    approvals.record_finding(ledger, "entity-outside-document-scope:class:Dev", "accepted", by="reviewer")
    _enable(tmp_cfg)
    agent = FakeAgent([])
    assert coverage_triage.triage(tmp_cfg, report, ledger, agent=agent) == {} and agent.calls == []
    tmp_cfg.raw["review"]["coverage_triage"]["agent"] = {"kind": "dry-run"}
    judged = coverage_triage.triage(tmp_cfg, report, {}, agent=agent)
    assert agent.calls == [] and next(iter(judged.values()))["decision"] == "unsure"


def test_설정_오류는_조용히_넘기지_않는다(tmp_cfg):
    tmp_cfg.raw["review"] = {"coverage_triage": {"enabled": True, "pass_gates": True}}
    with pytest.raises(ValueError, match="coverage_triage"):
        coverage_triage.settings(tmp_cfg)
    tmp_cfg.raw["review"] = {"coverage_triage": {"enabled": True, "agent": {"modle": "x"}}}
    with pytest.raises(ValueError, match="modle"):
        coverage_triage.triage(tmp_cfg, None, {})


def _steps(model_for):
    def extract(cfg):
        sha = resolve_commit(cfg.source_root, "HEAD")
        model = model_for(sha)
        model.save(cfg.facts_path)
        return model
    return update.Steps(prepare_compdb=lambda cfg, sha: None, extract=extract,
                        generate=lambda cfg, model, report: None)


def _model(sha):
    return KnowledgeModel(meta={"source_commit": sha}, classes={"Dev": ClassInfo("Dev", Location("dev.h", 5))})


def test_update_는_include_만_바뀐_커밋을_사람_없이_지나간다(tmp_cfg, header_repo):
    _model(header_repo[0]).save(tmp_cfg.facts_path)
    result = update.run_update(tmp_cfg, to=header_repo[1], steps=_steps(_model), log=lambda _: None)
    assert result.exit_code == 0 and result.processed == [header_repo[1]]
    assert "## 자동 분류한 변경" in (tmp_cfg.build_dir / "impact-review.md").read_text(encoding="utf-8")


def test_update_는_pass_gate_일_때만_LLM_범위_밖_판정으로_관문을_통과한다(tmp_cfg, header_repo, monkeypatch):
    _model(header_repo[1]).save(tmp_cfg.facts_path)
    monkeypatch.setattr(coverage_triage, "Agent", lambda *a, **k: FakeAgent(
        ['{"decision": "out-of-scope", "reason": "내부 포인터 타입 변경입니다."}']))
    _enable(tmp_cfg)
    stopped = update.run_update(tmp_cfg, to=header_repo[2], steps=_steps(_model), log=lambda _: None)
    assert stopped.exit_code == 2
    _enable(tmp_cfg, pass_gate=True)          # 같은 비교 범위의 판정은 기록에서 재사용한다
    passed = update.run_update(tmp_cfg, to=header_repo[2], steps=_steps(_model), log=lambda _: None)
    assert passed.exit_code == 0 and passed.processed == [header_repo[2]]
    assert approvals.load(tmp_cfg)["findings"] == {}           # 승인으로 기록하지 않았다
