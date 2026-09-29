import copy

import pytest

from sdd.facts.model import Location, Message, Scenario
from sdd.scenario_document import build


def scenario():
    messages = [Message("HAL", "Worker", f"work{i}", Location("hal.cpp", i + 1)) for i in range(75)]
    messages += [Message("HAL", "BackendA", "queue", Location("hal.cpp", 90), "virtual 후보"),
                 Message("HAL", "BackendB", "queue", Location("hal.cpp", 90), "virtual 후보"),
                 Message("HAL", "Worker", "run", Location("hal.cpp", 91), "예약된 호출, 실행 순서는 정적으로 확인 불가")]
    return Scenario("request", "요청", "HAL::request()", messages=messages, deferred=1)


def test_all_records_survive_presentation_and_hidden_boundaries_stay_visible():
    sc = scenario()
    original = copy.deepcopy(sc)
    doc = build(sc, {"hide": {"names": ["work*", "queue", "run"]}})
    assert sc == original
    assert doc.hidden == 75  # Boundaries are not filtered, even by a wildcard.
    for message in sc.messages:
        assert f"`{message.loc.cite()}`" in doc.details
    assert "76–78 / 78개" in doc.details
    assert "BackendA::queue()" in doc.overview and "BackendB::queue()" in doc.overview
    assert "sequenceDiagram" not in doc.overview
    assert "동기·비동기 여부는 호출부에서 확인" in doc.details
    assert "즉시 실행되는 호출이 아닙니다" not in doc.details
    assert "이후 단계는 생략" not in doc.details


def test_focus_selects_late_calls_and_requires_actual_evidence():
    sc = scenario()
    settings = {"focus": [{"title": "후반 처리", "names": ["work74"], "src": "HAL"}]}
    doc = build(sc, settings)
    assert "Worker::work74()" in doc.overview
    assert "Worker::work0()" not in doc.overview
    sc.messages[74].name = "renamed"
    with pytest.raises(ValueError, match="호출 근거가 없습니다"):
        build(sc, settings)


def test_focus_does_not_hide_node_overflow_or_collapse_same_named_calls():
    sc = scenario()
    settings = {"focus": [{"title": "분기", "names": ["queue"]}]}
    with pytest.raises(RuntimeError, match="nodes"):
        build(sc, settings, max_nodes=2)
    sc.messages[1] = Message("HAL", "Worker", "work0", Location("hal.cpp", 2))
    doc = build(sc, {})
    assert "`hal.cpp:1`" in doc.details and "`hal.cpp:2`" in doc.details


def test_site_and_carryover_reject_changed_scenario_evidence(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.export_site import export_site
    from sdd.carryover import carry_forward

    tmp_cfg.sections_file.write_text('''sections:
  - id: scenarios
    title: 시나리오
    kind: per-scenario
    output: scenarios/index.md
    next: {title: 시나리오, link: scenarios/index.md}
''', encoding="utf-8")
    sample_model.save(tmp_cfg.facts_path)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    site = export_site(tmp_cfg)
    assert (site / "scenarios/process_capture_request.mmd").is_file()
    manifest = (site / "site-manifest.json").read_bytes()
    sc = sample_model.scenarios["process_capture_request"]
    # Same citation, changed call: citation-only checks cannot catch this.
    sc.messages[0].name = "destroyFrame"
    sample_model.save(tmp_cfg.facts_path)
    with pytest.raises(RuntimeError, match="Scenario evidence changed"):
        export_site(tmp_cfg)
    assert (site / "site-manifest.json").read_bytes() == manifest
    sample_model.meta["source_commit"] = "new"
    promoted, stale = carry_forward(tmp_cfg, sample_model, [])
    assert any(p.name == "process_capture_request.md" for p, _ in stale)


def test_scenario_defaults_to_facts_without_model_calls(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.export_html import _split

    class NoModel:
        def chat(self, *args, **kwargs):
            pytest.fail("A static scenario must not invoke the LLM")

    tmp_cfg.agent.kind = "ollama"
    section = {"id": "scenarios", "title": "시나리오", "kind": "per-scenario"}
    paths = Generator(tmp_cfg, sample_model, NoModel())._per_scenario(section, None)
    meta, _ = _split(paths[0].read_text(encoding="utf-8"))
    assert meta["generation_method"] == "extracted-scenario"
    assert meta["status"] == "ok" and "agent" not in meta
    # Other configured entries are absent; a partly populated index is not OK.
    index, body = _split(paths[-1].read_text(encoding="utf-8"))
    assert index["status"] == "needs-review" and "facts에 없습니다" in body


def test_deterministic_pages_do_not_claim_llm_authorship_and_can_carry_forward(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.carryover import carry_forward
    from sdd.export_html import _split
    from sdd.document_metadata import generation_method

    sec = next(s for s in tmp_cfg.sections() if s["id"] == "feature-flags")
    page = Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent))._flags_table(sec)
    meta, body = _split(page.read_text(encoding="utf-8"))
    assert meta["generation_method"] == "deterministic" and "agent" not in meta
    assert "추출 사실과 설정으로 생성" in body
    sample_model.meta["source_commit"] = "new"
    promoted, stale = carry_forward(tmp_cfg, sample_model, [])
    assert page in promoted and not stale
    assert generation_method({"design_topics": [{"statements": []}]}, "ollama") == "source-bound-contract"
    assert generation_method({"narration": "facts"}, "ollama") == "extracted-structure"
    assert generation_method({"design_topics": [{"statements": []}, {}]}, "ollama") == "mixed"
