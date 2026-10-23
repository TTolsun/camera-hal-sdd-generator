"""narration: facts 인 패키지별 색인: LLM 없이 facts 표만 만들고, 고른 패키지만 싣고, 범위 검사도 같은 기준을 쓴다."""

import yaml

from sdd.document_metadata import generation_method
from sdd.facts.model import ClassInfo, FunctionInfo, KnowledgeModel, Location, PackageInfo
from sdd.generate import Generator
from sdd.impact import compute

INDEX = {"id": "index-pkg", "title": "구성 요소 색인", "output": "component-index.md", "kind": "per-package",
         "narration": "facts", "lead": "패키지별로 찾으세요.",
         "facts": {"classes": ["*"], "functions": ["*"], "packages": ["src/*"]}}


class _NoModel:
    def chat(self, *args, **kwargs):
        raise AssertionError("narration: facts 는 모델을 부르지 않는다")


def _model():
    m = KnowledgeModel(meta={"source_commit": "abc"})
    m.classes["Pipe"] = ClassInfo("Pipe", Location("src/pipe/pipe.h", 3), package="src/pipe", brief="Moves frames")
    m.classes["Cam"] = ClassInfo("Cam", Location("src/cam/cam.h", 7), package="src/cam", bases=["Pipe"])
    m.classes["drm_mode"] = ClassInfo("drm_mode", Location("include/linux/drm.h", 9), package="include/linux")
    m.functions["logCategoryLsc"] = FunctionInfo("logCategoryLsc", def_loc=Location("src/pipe/lsc.cpp", 12))
    m.functions["helper"] = FunctionInfo("helper", Location("src/tools/helper.h", 4), brief="Formats ids")
    m.functions["drm_ioctl"] = FunctionInfo("drm_ioctl", Location("include/linux/drm.h", 30))
    m.packages = {"src/pipe": PackageInfo("src/pipe", "src/pipe", ["Pipe"]),
                  "src/cam": PackageInfo("src/cam", "src/cam", ["Cam"]),
                  "include/linux": PackageInfo("include/linux", "include/linux", ["drm_mode"])}
    return m


def _sections(cfg, values):
    cfg.sections_file.write_text(yaml.safe_dump({"sections": values}, allow_unicode=True), encoding="utf-8")


def test_facts_색인은_모델_없이_고른_패키지의_클래스_표만_만든다(tmp_cfg):
    _sections(tmp_cfg, [INDEX])
    Generator(tmp_cfg, _model(), _NoModel()).run()
    page = (tmp_cfg.sdd_dir / "component-index.md").read_text(encoding="utf-8")
    assert "status: ok" in page and "generation_method: extracted-structure" in page
    assert "## src/cam" in page and "## src/pipe" in page and "include/linux" not in page
    assert "| `Cam` | `src/cam/cam.h:7` | `Pipe` | 확인 필요 |" in page
    assert "| `Pipe` | `src/pipe/pipe.h:3` | – | Moves frames |" in page
    assert generation_method(INDEX, "ollama") == "extracted-structure"


def test_선언_위치가_없는_클래스가_있으면_확인_필요로_남긴다(tmp_cfg):
    model = _model()
    model.classes["Pipe"].loc = None
    _sections(tmp_cfg, [INDEX])
    Generator(tmp_cfg, model, _NoModel()).run()
    assert "status: needs-review" in (tmp_cfg.sdd_dir / "component-index.md").read_text(encoding="utf-8")


def test_범위_검사는_색인이_싣지_않는_패키지의_클래스를_다룬다고_보지_않는다(tmp_cfg):
    _sections(tmp_cfg, [INDEX])
    model = _model()
    report = compute(tmp_cfg, model, ["src/cam/cam.h", "include/linux/drm.h"], "a", "b", non_semantic={})
    # include/linux 는 색인이 싣지 않으므로 그 파일의 클래스와 함수는 검토 항목으로 남는다.
    assert sorted(f["name"] for f in report.coverage["findings"]) == ["drm_ioctl", "drm_mode"]
    assert "index-pkg" in {s for e in report.coverage["entities"] if e["name"] == "Cam" for s in e["sections"]}


def test_facts_색인은_자유_함수도_선언_파일의_패키지로_싣는다(tmp_cfg):
    tmp_cfg.package_depth = 2
    _sections(tmp_cfg, [INDEX])
    Generator(tmp_cfg, _model(), _NoModel()).run()
    page = (tmp_cfg.sdd_dir / "component-index.md").read_text(encoding="utf-8")
    assert "| `logCategoryLsc` | – | `src/pipe/lsc.cpp:12` | 확인 필요 |" in page
    assert "## src/tools" in page and "| `helper` | `src/tools/helper.h:4` | – | Formats ids |" in page
    assert "drm_ioctl" not in page


def test_범위_검사는_색인의_함수도_같은_패키지_규칙으로_판정한다(tmp_cfg):
    tmp_cfg.package_depth = 2
    _sections(tmp_cfg, [INDEX])
    report = compute(tmp_cfg, _model(), ["src/pipe/lsc.cpp", "include/linux/drm.h"], "a", "b", non_semantic={})
    assert sorted(f["name"] for f in report.coverage["findings"]) == ["drm_ioctl", "drm_mode"]
