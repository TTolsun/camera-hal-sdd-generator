"""빌드 파일 변경의 효과가 분석한 빌드 안에서 모두 검사될 때만 그 변경을 자동 분류한다."""

import subprocess

import yaml

from sdd.facts.model import ClassInfo, KnowledgeModel, Location
from sdd.impact import compute
from sdd.impact_review import review_markdown


def _cfg(cfg):
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [{"id": "api", "facts": {"classes": ["*"]}}]}),
                                 encoding="utf-8")
    return cfg


def _model(units, parsed, classes=("Dev",)):
    m = KnowledgeModel(classes={c: ClassInfo(c, Location(f"{c.lower()}.h", 1)) for c in classes})
    if units is not None:
        m.meta["compile_units"] = units
    if parsed is not None:
        m.meta["parsed_files"] = parsed
    return m


BASE = _model({"dev.cpp": "a1"}, ["dev.cpp", "dev.h"])


def _findings(cfg, head, files, base=BASE):
    report = compute(cfg, head, files, "a", "b", base, non_semantic={})
    return report, [f["name"] for f in report.coverage["findings"]]


def test_새_TU_를_더하는_빌드_파일_변경은_자동_분류한다(tmp_cfg):
    head = _model({"dev.cpp": "a1", "lsc.cpp": "b2"}, ["dev.cpp", "dev.h", "lsc.cpp"])
    head.classes["Lsc"] = ClassInfo("Lsc", Location("lsc.cpp", 3))
    report, findings = _findings(_cfg(tmp_cfg), head, ["meson.build", "lsc.cpp"])
    assert findings == []
    assert [(c["name"], c["classification"]) for c in report.coverage["classified"]] == [
        ("meson.build", "build-change-visible-in-analyzed-build")]
    assert "분석한 빌드에서 모두 검사됨" in review_markdown(report)


def test_효과가_검사되지_않는_빌드_파일_변경은_검토로_남긴다(tmp_cfg):
    cfg = _cfg(tmp_cfg)
    # 기존 TU 의 컴파일 인자(-D 등)가 바뀜
    assert _findings(cfg, _model({"dev.cpp": "zz"}, ["dev.cpp", "dev.h"]), ["Android.mk"])[1] == ["Android.mk"]
    # 바뀌지 않은 파일이 새로 빌드됨: 그 파일의 클래스는 이번 범위 검사를 받지 않는다
    newly_built = _model({"dev.cpp": "a1", "old.cpp": "c3"}, ["dev.cpp", "dev.h", "old.cpp"])
    assert _findings(cfg, newly_built, ["Android.mk"])[1] == ["Android.mk"]
    # 빌드가 만든 헤더의 내용이 바뀜
    gen_base = _model({"dev.cpp": "a1", "generated:build/config.h": "g1"}, ["dev.cpp", "build/config.h"])
    gen_head = _model({"dev.cpp": "a1", "generated:build/config.h": "g2"}, ["dev.cpp", "build/config.h"])
    assert _findings(cfg, gen_head, ["meson.build"], gen_base)[1] == ["meson.build"]
    # 이전 facts 에 기록이 없음
    assert _findings(cfg, _model({"dev.cpp": "a1"}, ["dev.cpp"]), ["meson.build"],
                     _model(None, ["dev.cpp"]))[1] == ["meson.build"]


def test_빌드_파일이_아닌_비코드_파일은_이_규칙을_쓰지_않는다(tmp_cfg):
    head = _model({"dev.cpp": "a1"}, ["dev.cpp", "dev.h"])
    assert _findings(_cfg(tmp_cfg), head, ["data/tuning.yaml"])[1] == ["data/tuning.yaml"]


def test_추출이_TU_인자와_빌드가_만든_입력의_지문을_남긴다(tmp_cfg):
    from sdd.extract import _compile_units
    root = tmp_cfg.source_root
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "dev.cpp").write_text("int x;\n", encoding="utf-8")
    subprocess.run(["git", "add", "dev.cpp"], cwd=root, check=True)
    (root / "gen.h").write_text("#define A 1\n", encoding="utf-8")       # 추적되지 않는 생성 파일
    entries = [{"directory": str(root), "file": "dev.cpp", "arguments": ["c++", "-DA=1", "-c", "dev.cpp"]}]
    first = _compile_units(tmp_cfg, entries, ["dev.cpp", "gen.h"])
    assert set(first) == {"dev.cpp", "generated:gen.h"}
    entries[0]["arguments"][1] = "-DA=2"
    (root / "gen.h").write_text("#define A 2\n", encoding="utf-8")
    second = _compile_units(tmp_cfg, entries, ["dev.cpp", "gen.h"])
    assert first["dev.cpp"] != second["dev.cpp"] and first["generated:gen.h"] != second["generated:gen.h"]
