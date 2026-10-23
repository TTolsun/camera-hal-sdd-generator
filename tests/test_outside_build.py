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
    assert sorted((c["name"], c["classification"]) for c in report.coverage["classified"]) == [
        ("app/sdl.h", "outside-analyzed-build"), ("app/sdl_sink.cpp", "outside-analyzed-build")]
    assert "분석한 빌드에서 컴파일되지 않음" in review_markdown(report)


def test_빌드_파일과_빌드에서_빠진_파일과_기록이_없는_facts_는_분류하지_않는다(tmp_cfg):
    cfg = _cfg(tmp_cfg)
    build_file = compute(cfg, _model(["dev.cpp"]), ["app/meson.build"], "a", "b", _model(["dev.cpp"]), non_semantic={})
    assert [f["name"] for f in build_file.coverage["findings"]] == ["app/meson.build"]
    removed = compute(cfg, _model(["dev.cpp"]), ["old.cpp"], "a", "b", _model(["dev.cpp", "old.cpp"]), non_semantic={})
    assert [f["name"] for f in removed.coverage["findings"]] == ["old.cpp"]
    unknown = compute(cfg, _model(None), ["app/sdl_sink.cpp"], "a", "b", _model(None), non_semantic={})
    assert [f["name"] for f in unknown.coverage["findings"]] == ["app/sdl_sink.cpp"]


def test_이전_facts_에_기록이_없으면_분류하지_않는다(tmp_cfg):
    report = compute(_cfg(tmp_cfg), _model(["dev.cpp"]), ["app/sdl_sink.cpp"], "a", "b", _model(None), non_semantic={})
    assert [f["name"] for f in report.coverage["findings"]] == ["app/sdl_sink.cpp"]


def test_수동_문서의_근거_파일은_빌드_밖이어도_검토로_남긴다(tmp_cfg):
    cfg = _cfg(tmp_cfg)
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [
        {"id": "api", "facts": {"classes": ["Dev"]}},
        {"id": "notes", "kind": "manual", "output": "notes.md"}]}), encoding="utf-8")
    cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
    (cfg.sdd_dir / "notes.md").write_text("---\nevidence_files: [app/sdl_sink.cpp]\n---\n\n본문\n", encoding="utf-8")
    report = compute(cfg, _model(["dev.cpp"]), ["app/sdl_sink.cpp"], "a", "b", _model(["dev.cpp"]), non_semantic={})
    assert [f["name"] for f in report.coverage["findings"]] == ["app/sdl_sink.cpp"]


def test_빌드_밖_파일은_watch_로_문서를_다시_만들지_않는다(tmp_cfg):
    cfg = _cfg(tmp_cfg)
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [{"id": "api", "facts": {"classes": ["Dev"]},
                                                                "watch": ["app/**"]}]}), encoding="utf-8")
    report = compute(cfg, _model(["dev.cpp"]), ["app/sdl_sink.cpp", "app/main.cpp"], "a", "b",
                     _model(["dev.cpp", "app/main.cpp"]), non_semantic={})
    assert report.sections == {"api": ["watch 일치: app/main.cpp"]}


def test_분류_목록에_같은_파일이_두_번_나오지_않는다(tmp_cfg):
    report = compute(_cfg(tmp_cfg), _model(["dev.cpp"]), ["app/a.cpp", "app/b.h"], "a", "b",
                     _model(["dev.cpp"]), non_semantic={})
    assert sorted(c["name"] for c in report.coverage["classified"]) == ["app/a.cpp", "app/b.h"]


def test_소스_루트_판정은_경로_요소와_링크_경로를_쓴다(tmp_path):
    from sdd.facts.comments import root_relative
    root = tmp_path / "src"
    (root / "..generated").mkdir(parents=True)
    roots = (str(root),)
    assert root_relative(str(root / "..generated" / "ids.h"), roots) == "..generated/ids.h"
    assert root_relative(str(tmp_path / "outside.h"), roots) is None
    assert root_relative(str(root / "a" / ".." / "b.h"), roots) == "b.h"
