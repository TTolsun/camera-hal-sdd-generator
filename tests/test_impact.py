import pytest
import yaml

from sdd.impact import compute
from sdd.matching import glob_to_regex, match_any


def test_glob_double_star_matches_any_depth():
    assert match_any("a.h", ["**/*.h"])
    assert match_any("x/y/z.h", ["**/*.h"])
    assert not match_any("x/y/z.cpp", ["**/*.h"])
    assert glob_to_regex("Android.mk").match("Android.mk")
    assert not glob_to_regex("Android.mk").match("jni/Android.mk")
    assert match_any("jni/Android.mk", ["**/Android.mk"])


def test_impact_maps_changed_class_to_sections_and_scenarios(tmp_cfg, sample_model):
    report = compute(tmp_cfg, sample_model, ["device/CameraDevice.cpp"], base="HEAD~1", head="HEAD")
    assert "CameraDevice" in report.changed_classes
    assert "device" in report.packages
    # components 는 watch(**/*.cpp) 와 클래스 규칙 둘 다에 걸린다.
    assert "components" in report.sections
    assert any("클래스 변경" in r for r in report.sections["components"])
    # 시나리오 경로에 포함된 파일이므로 시나리오도 영향 대상이다.
    assert "process_capture_request" in report.scenarios
    assert "scenarios" in report.sections
    # threading 은 watch 도 클래스 패턴도 맞지 않는다.
    assert "threading" not in report.sections


def test_impact_header_only_change_hits_overview(tmp_cfg, sample_model):
    report = compute(tmp_cfg, sample_model, ["pipeline/PipeThread.h"], base="a", head="b")
    assert "overview" in report.sections
    assert "threading" in report.sections
    assert "process_capture_request" not in report.scenarios


def test_impact_classes_override_keeps_overview_out_of_symbol_rule(tmp_cfg, sample_model):
    # overview 는 classes: ["*"] 를 인용용으로만 넘기고 impact_classes: [] 로 심볼 규칙에서 뺀다.
    report = compute(tmp_cfg, sample_model, ["pipeline/FrameFactory.cpp"], base="a", head="b")
    assert "overview" not in report.sections
    assert "components" in report.sections


@pytest.mark.parametrize("source_file", ["pipeline/Pipe.cpp", "config/tuning.yaml", "include/removed.h"])
@pytest.mark.parametrize("prefix", ["", "./"])
def test_contract_source_change_selects_page_without_watch_or_symbols(tmp_cfg, sample_model, source_file, prefix):
    # A prose contract can reference files outside Clang's parsed-file inventory.
    sample_model.meta["parsed_files"] = ["device/CameraDevice.cpp"]
    tmp_cfg.sections_file.write_text(yaml.safe_dump({"sections": [
        {"id": "contract", "kind": "prose", "facts": {}, "watch": ["unrelated/**"],
         "design_topics": [{"id": "lifecycle", "sources": [{"id": "impl", "file": prefix + source_file}]}]},
        {"id": "other", "kind": "prose", "facts": {},
         "design_topics": [{"id": "other", "sources": [{"id": "impl", "file": "other.cpp"}]}]},
    ]}), encoding="utf-8")
    report = compute(tmp_cfg, sample_model, [source_file], base="a", head="b", non_semantic={})
    assert set(report.sections) == {"contract"}
    assert report.sections["contract"] == [f"설계 근거 파일 변경: {source_file}"]
    assert report.base == "a" and report.head == "b"
