"""사내 설정 템플릿이 생성기가 읽을 수 있는 설정인지 확인한다."""

from pathlib import Path

from sdd import coverage_triage, document_health
from sdd.config import load
from sdd.document_metadata import generation_method

TEMPLATE = Path(__file__).resolve().parents[1] / "examples" / "inhouse-template"


def test_템플릿_설정을_읽고_검사_설정이_유효하다():
    cfg = load(TEMPLATE / "sdd.yaml")
    assert cfg.ndk_build["enabled"] is True
    # update 는 compdb_cmd 없이 ndk_build 의 project_dir·args 로 DB 를 다시 만든다.
    assert "compdb_cmd" not in (cfg.raw.get("update") or {})
    assert cfg.raw["site"]["require_approval"] is False
    coverage_triage.settings(cfg)
    document_health.settings(cfg)
    assert cfg.prompts_dir.name == "prompts" and "camera-hal-sdd-generator" in cfg.prompts_dir.as_posix()


def test_템플릿의_구성_요소_색인은_모델_없이_모든_클래스와_함수를_싣는다():
    cfg = load(TEMPLATE / "sdd.yaml")
    components = next(s for s in cfg.sections() if s["id"] == "components")
    assert components["kind"] == "per-package" and components["narration"] == "facts"
    assert components["facts"]["classes"] == ["*"] and components["facts"]["functions"] == ["*"]
    assert generation_method(components, "dry-run") == "extracted-structure"
    assert [s["id"] for s in cfg.scenarios()] == ["configure_streams", "process_capture_request", "flush"]


def test_템플릿에는_채울_자리만_있고_사내_값은_없다():
    text = "\n".join(p.read_text(encoding="utf-8") for p in TEMPLATE.rglob("*") if p.is_file())
    assert "<namespace>" in text and "<사내 코드 열람 주소>" in text


def test_템플릿은_원고와_승인_장부와_mermaid_사본을_git_에_남긴다():
    ignored = (TEMPLATE / ".gitignore").read_text(encoding="utf-8").split()
    assert "build/" in ignored and "sdd.local.yaml" in ignored
    assert not {"sdd/", "assets/"} & set(ignored)
