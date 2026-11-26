import json
import subprocess
from argparse import Namespace

import pytest
import yaml

from sdd import first_run
from sdd.facts.model import ClassInfo, FunctionInfo, KnowledgeModel, Location, Message, Method, Scenario
from sdd.generate import Generator
from sdd.generation_run import Execution
from sdd.impact import ImpactReport


def _git(path, *args):
    return subprocess.check_output(["git", *args], cwd=path, encoding="utf-8").strip()


@pytest.fixture
def initial(tmp_cfg):
    cfg = tmp_cfg
    cfg.raw["first_run_inputs"] = True
    cfg.agent.kind = "cli"
    cfg.agent.max_input_chars = 6000
    cfg.scenarios_file.write_text("scenarios: []\n", encoding="utf-8")
    source = cfg.source_root / "device.cpp"
    source.write_text("void stopCaptureBuffer() {\n  cancelPending();\n  emitCompletion();\n}\n", encoding="utf-8")
    _git(cfg.source_root, "init", "-q")
    _git(cfg.source_root, "add", "device.cpp")
    _git(cfg.source_root, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-qm", "source")
    model = KnowledgeModel(meta={"source_commit": _git(cfg.source_root, "rev-parse", "HEAD")})
    model.functions["stopCaptureBuffer"] = FunctionInfo("stopCaptureBuffer", def_loc=Location("device.cpp", 1))
    model.save(cfg.facts_path)
    cfg.sections_file.write_text(yaml.safe_dump({
        "sections": [_section("selected", "completion", "ownership"), _section("other", "completion")],
    }, allow_unicode=True), encoding="utf-8")
    return cfg, model, source


def _section(sid, *topics):
    return {"id": sid, "title": sid, "design_generation": "llm",
            "design_requirements": [{"id": topic, "question": f"{topic}?"} for topic in topics],
            "design_topics": [{"id": topic, "title": topic, "question": f"{topic}?",
                               "covers": [topic], "sources": []} for topic in topics]}


class Selected:
    last_receipt = None
    last_cli_attempt = None

    def __init__(self, cfg, *, fail_at=0, missing=False):
        self.cfg, self.fail_at, self.missing = cfg.agent, fail_at, missing
        self.tags = []

    def chat(self, system, user, *, tag, response_schema):
        self.tags.append(tag)
        if self.fail_at == len(self.tags):
            raise RuntimeError("interrupted")
        entries = json.loads(user)["candidates"]
        assert any("cancelPending()" in value["text"] for value in entries.values())
        return json.dumps({"question": "정지 중 언제 취소를 통지합니까?",
                           "sources": [] if self.missing else [next(iter(entries))],
                           "missing": "취소 근거가 없습니다." if self.missing else ""})


def test_selected_generation_binds_git_sources_without_editing_inputs(initial, monkeypatch):
    cfg, model, source = initial
    original = cfg.sections_file.read_bytes()
    head = model.meta["source_commit"]
    source.write_text("working-tree-only\n", encoding="utf-8")
    agent = Selected(cfg)

    def check(self, sections, impact):
        assert sections == ["selected"]
        assert all(t["sources"] for t in cfg.section("selected")["design_topics"])
        assert not cfg.section("other")["design_topics"][0]["sources"]
        assert set(model.evidence) == {"selected/completion/window-1", "selected/ownership/window-1"}
        assert all(r["commit"] == head and "cancelPending()" in r["text"] for r in model.evidence.values())
        return []

    monkeypatch.setattr(Generator, "_run", check)
    Generator(cfg, model, agent).run(["selected"])
    assert len(agent.tags) == 2
    assert cfg.sections_file.read_bytes() == original
    assert first_run.pending(cfg, ["selected"]) == []


def test_completed_input_is_saved_before_recoverable_interrupt(initial):
    cfg, model, _ = initial
    interrupted = Selected(cfg, fail_at=2)
    with pytest.raises(RuntimeError, match="interrupted"):
        first_run.prepare(cfg, model, first_run.pending(cfg, ["selected"]), Execution(cfg, interrupted, model=model))
    checkpoint = json.loads(first_run.catalog_path(cfg).read_bytes())
    assert set(checkpoint["topics"]) == {"selected/completion"}
    retry = Selected(cfg)
    first_run.prepare(cfg, model, first_run.pending(cfg, ["selected"]), Execution(cfg, retry, model=model))
    assert retry.tags == ["first_run_selected_ownership_0"]


def test_missing_source_keeps_template_and_previous_document(initial):
    cfg, model, _ = initial
    cfg.sdd_dir.mkdir()
    existing = cfg.sdd_dir / "selected.md"
    existing.write_bytes(b"prior")
    with pytest.raises(ValueError, match="근거 부족"):
        Generator(cfg, model, Selected(cfg, missing=True)).run(["selected"])
    assert existing.read_bytes() == b"prior"
    assert not first_run.catalog_path(cfg).exists()


def test_plan_has_no_catalog_and_revision_change_invalidates_saved_inputs(initial):
    cfg, model, source = initial
    missing = first_run.pending(cfg, ["selected"])
    plan = json.loads(first_run.plan(cfg, model, missing).read_bytes())
    assert plan["model_calls"] == 0
    assert not first_run.catalog_path(cfg).exists()
    first_run.prepare(cfg, model, missing, Execution(cfg, Selected(cfg), model=model))
    source.write_text(source.read_text(encoding="utf-8") + "// revision\n", encoding="utf-8")
    _git(cfg.source_root, "add", "device.cpp")
    _git(cfg.source_root, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-qm", "change")
    assert len(first_run.pending(cfg, ["selected"])) == 2
    with pytest.raises(ValueError, match="Git HEAD"):
        first_run.plan(cfg, model, first_run.pending(cfg, ["selected"]))
    cfg.sdd_dir.mkdir()
    (cfg.sdd_dir / "selected.md").write_bytes(b"prior")
    change = ImpactReport(base=model.meta["source_commit"], head=_git(cfg.source_root, "rev-parse", "HEAD"))
    first_run.extend_impact(cfg, change)
    assert set(change.sections) == {"selected"}


def test_generation_and_first_run_share_the_call_budget(initial, monkeypatch):
    cfg, model, _ = initial
    cfg.raw["review"]["max_calls"] = 2
    agent = Selected(cfg)

    def try_generation(self, sections, impact):
        self.agent.chat("generation", "one more call", tag="writing", response_schema={})

    monkeypatch.setattr(Generator, "_run", try_generation)
    with pytest.raises(RuntimeError, match="run call budget"):
        Generator(cfg, model, agent).run(["selected"])
    assert len(agent.tags) == 2
    assert first_run.pending(cfg, ["selected"]) == []


def test_cli_plan_only_leaves_facts_and_sources_unmodified(initial, monkeypatch):
    from sdd.cli import cmd_generate
    cfg, _, _ = initial
    before = cfg.facts_path.read_bytes()
    monkeypatch.setattr("sdd.cli._cfg", lambda _: cfg)
    assert cmd_generate(Namespace(sections="selected", plan_only=True, from_impact=False)) == 0
    assert cfg.facts_path.read_bytes() == before
    assert not first_run.catalog_path(cfg).exists()
    plan = json.loads((cfg.build_dir / "first-run-plan.json").read_bytes())
    assert plan["pending"] == ["selected/completion", "selected/ownership"]


def test_custom_sources_override_automatically_prepared_questions(initial):
    cfg, model, _ = initial
    first_run.prepare(cfg, model, first_run.pending(cfg, ["selected"]), Execution(cfg, Selected(cfg), model=model))
    authored = {
        "id": "caller", "file": "device.cpp",
        "start": "void stopCaptureBuffer()", "end": "emitCompletion();",
    }
    data = yaml.safe_load(cfg.sections_file.read_bytes())
    topic = data["sections"][0]["design_topics"][0]
    topic.update(question="사람이 지정한 질문입니까?", sources=[authored])
    cfg.sections_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cfg.section("selected")["design_topics"][0] == topic
    assert not first_run.pending(cfg, ["selected"])


def test_candidate_cannot_name_an_unsupplied_source():
    response = json.dumps({"question": "어떤 조건에서 반환합니까?", "sources": ["foreign"], "missing": ""})
    with pytest.raises(ValueError, match="후보 ID"):
        first_run._response(response, "selected/completion", {"window-1": {}})


def test_figure_selection_reports_measured_retry_choices(initial, monkeypatch):
    from sdd import first_run_visual_budget as budget
    cfg, model, _ = initial
    section, topic = first_run.pending(cfg, ["selected"])[0]
    ids = ["window-1", "window-2", "window-3", "window-4", "window-5"]
    selectors = {key: {"id": key} for key in ids}
    history = []

    def estimate(cfg, model, files, section, topic, sources, figures):
        return 2400 + 1000 * len(sources)

    def chat(system, user, *, tag, response_schema):
        details = json.loads(user)["figure_selection"]
        assert details["max_windows"] == response_schema["properties"]["sources"]["maxItems"]
        assert all(row["diagram_chars"] <= cfg.agent.max_input_chars for row in details["measured_examples"])
        history.append(details)
        selected = ids[:4] if len(history) == 1 else details["measured_examples"][0]["ids"]
        return json.dumps({"question": "어떤 조건에서 취소를 통지합니까?", "sources": selected, "missing": ""})

    monkeypatch.setattr(budget, "visual_size", estimate)
    from types import SimpleNamespace
    _, selected = budget.select(cfg, model, {}, section, topic, SimpleNamespace(chat=chat),
                                "{}", selectors, "ownership", [{"topic": topic["id"]}])
    assert [row["max_windows"] for row in history] == [4, 3]
    assert history[1]["previous_ids"] == ids[:4]
    assert history[1]["previous_diagram_chars"] == 6400
    assert len(selected) == 3


def test_figure_can_fit_with_only_a_later_candidate():
    from sdd.first_run_visual_budget import examples
    keys = [f"window-{n}" for n in range(1, 17)]
    assert examples(keys, lambda ids: 20 if ids == ("window-16",) else 40, 30, 4, []) == [
        {"ids": ("window-16",), "diagram_chars": 20},
    ]


def test_missing_evidence_expands_to_fresh_windows_once(initial, monkeypatch):
    cfg, model, _ = initial
    seen = []

    def candidates(*args):
        for n in range(1, 20):
            yield {"file": "device.cpp", "text": f"source window {n}"}, {"file": "device.cpp", "start": "start", "end": "end"}

    class Retry(Selected):
        def chat(self, system, user, *, tag, response_schema):
            payload = json.loads(user)
            seen.append(payload)
            if len(seen) == 1:
                return json.dumps({"question": "", "sources": [], "missing": "completion state is missing"})
            assert payload["previous_gap"].endswith("completion state is missing")
            assert {"window-1", "window-17"} <= set(payload["candidates"])
            return json.dumps({"question": "취소 상태는 어디서 읽습니까?", "sources": ["window-17"], "missing": ""})

    monkeypatch.setattr(first_run, "_candidates", candidates)
    section, topic = first_run.pending(cfg, ["selected"])[0]
    first_run.prepare(cfg, model, [(section, topic)], Execution(cfg, Retry(cfg), model=model))
    assert len(seen) == 2
    assert "window-17" not in seen[0]["candidates"]
    assert cfg.section("selected")["design_topics"][0]["sources"][0]["id"] == "window-17"


def test_code_only_file_with_no_english_cue_supplies_pinned_fallback(initial):
    cfg, model, _ = initial
    model.functions = {"f": FunctionInfo("f", def_loc=Location("device.cpp", 1))}
    section, topic = first_run.pending(cfg, ["selected"])[0]
    candidates = list(first_run._candidates(cfg, first_run._locations(model), {},
                                            model.meta["source_commit"], section, topic))
    assert candidates and "cancelPending();" in candidates[0][0]["text"]


def test_scenario_call_and_definition_are_presented_together(initial):
    cfg, model, _ = initial
    definition = cfg.source_root / "provider.cpp"
    definition.write_text("void Provider::cancelPending() {\n  state = Cancelled;\n}\n", encoding="utf-8")
    _git(cfg.source_root, "add", "provider.cpp")
    _git(cfg.source_root, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-qm", "provider")
    commit = _git(cfg.source_root, "rev-parse", "HEAD")
    cls = ClassInfo("hal::Provider", methods=[Method("cancelPending", def_loc=Location("provider.cpp", 1))])
    model.classes[cls.name] = cls
    caller = Location("device.cpp", 2)
    model.scenarios["stop"] = Scenario("stop", "stop", "stopCaptureBuffer", messages=[
        Message("Device", "Provider", "cancelPending()", caller),
        Message("Device", "Provider", "cancelPending()", caller, "deferred"),
    ])
    pairs = list(first_run._scenario_pairs(model))
    assert len(pairs) == 1
    section, topic = first_run.pending(cfg, ["selected"])[0]
    locations = first_run._locations(model)
    candidates = list(first_run._candidates(cfg, locations, {}, commit, section, topic, pairs))
    payload, _ = first_run._request(cfg, section, topic, candidates)
    call, provider = list(json.loads(payload)["candidates"].values())[:2]
    assert call["call_pair"] == provider["call_pair"]
    assert (call["call_role"], provider["call_role"]) == ("call", "definition")
    assert "cancelPending();" in call["text"] and "state = Cancelled;" in provider["text"]
    payload, _ = first_run._request(cfg, section, topic, candidates[:1])
    assert not json.loads(payload)["candidates"]
    section["watch_exclude"] = ["provider.cpp"]
    assert all("call_pair" not in item for item, _ in first_run._candidates(
        cfg, locations, {}, commit, section, topic, pairs))
    other = ClassInfo("other::Provider", methods=[Method("cancelPending", def_loc=Location("other.cpp", 1))])
    model.classes[other.name] = other
    assert not list(first_run._scenario_pairs(model))
