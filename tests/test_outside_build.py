"""분석한 빌드에서 Clang 이 읽지 않은 C/C++ 파일의 변경은 문서 범위 판단 없이 분류한다."""

import yaml

from sdd.facts.model import ClassInfo, KnowledgeModel, Location
from sdd.impact import compute
from sdd.impact_review import review_markdown


def _cfg(cfg):
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [{"id": "api", "facts": {"classes": ["Dev"]}}]}),
                                 encoding="utf-8")
    return cfg


def _model(parsed):
    m = KnowledgeModel(classes={"Dev": ClassInfo("Dev", Location("dev.h", 3))})
    if parsed is not None:
        m.meta["parsed_files"] = parsed
    return m


def test_빌드가_읽지_않은_소스는_자동_분류한다(tmp_cfg):
    report = compute(_cfg(tmp_cfg), _model(["dev.cpp", "dev.h"]), ["app/sdl_sink.cpp", "app/sdl.h"], "a", "b",
                     _model(["dev.cpp", "dev.h"]), non_semantic={})
    assert report.coverage["findings"] == []
    assert {c["name"]: c["classification"] for c in report.coverage["classified"]} == {
        "app/sdl_sink.cpp": "outside-analyzed-build", "app/sdl.h": "outside-analyzed-build"}
    assert "분석한 빌드에서 컴파일되지 않음" in review_markdown(report)


def test_빌드_파일과_빌드에서_빠진_파일과_기록이_없는_facts_는_분류하지_않는다(tmp_cfg):
    cfg = _cfg(tmp_cfg)
    build_file = compute(cfg, _model(["dev.cpp"]), ["app/meson.build"], "a", "b", _model(["dev.cpp"]), non_semantic={})
    assert [f["name"] for f in build_file.coverage["findings"]] == ["app/meson.build"]
    removed = compute(cfg, _model(["dev.cpp"]), ["old.cpp"], "a", "b", _model(["dev.cpp", "old.cpp"]), non_semantic={})
    assert [f["name"] for f in removed.coverage["findings"]] == ["old.cpp"]
    unknown = compute(cfg, _model(None), ["app/sdl_sink.cpp"], "a", "b", _model(None), non_semantic={})
    assert [f["name"] for f in unknown.coverage["findings"]] == ["app/sdl_sink.cpp"]
