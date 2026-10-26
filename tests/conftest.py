from __future__ import annotations

from pathlib import Path

import pytest

from sdd.config import load
from sdd.facts.model import (ClassInfo, Define, KnowledgeModel, Location, Message, Method,
                             PackageInfo, Scenario)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_model() -> KnowledgeModel:
    m = KnowledgeModel(meta={"source_commit": "abc123"})
    m.packages["device"] = PackageInfo(name="device", path="device", classes=["CameraDevice"])
    m.packages["pipeline"] = PackageInfo(name="pipeline", path="pipeline", classes=["FrameFactory", "PipeThread"])
    m.classes["CameraDevice"] = ClassInfo(
        name="CameraDevice", loc=Location("device/CameraDevice.h", 40), package="device",
        methods=[Method("configureStreams", Location("device/CameraDevice.cpp", 120)),
                 Method("processCaptureRequest", Location("device/CameraDevice.cpp", 300))],
        brief="HAL3 디바이스 진입점")
    m.classes["FrameFactory"] = ClassInfo(
        name="FrameFactory", loc=Location("pipeline/FrameFactory.h", 12), package="pipeline",
        methods=[Method("createFrame", Location("pipeline/FrameFactory.cpp", 1240))])
    m.classes["PipeThread"] = ClassInfo(
        name="PipeThread", loc=Location("pipeline/PipeThread.h", 8), package="pipeline",
        bases=["Thread"], methods=[Method("threadLoop", Location("pipeline/PipeThread.cpp", 55))])
    m.defines["USE_SAT"] = Define("USE_SAT", "1", usages=[Location("device/CameraDevice.cpp", 310)])
    m.scenarios["process_capture_request"] = Scenario(
        id="process_capture_request", title="캡처 요청 처리",
        entry="CameraDevice::processCaptureRequest(camera3_capture_request_t *)",
        participants=["CameraDevice", "FrameFactory"],
        messages=[Message("CameraDevice", "FrameFactory", "createFrame", Location("device/CameraDevice.cpp", 305))],
        mermaid="sequenceDiagram\n  CameraDevice->>FrameFactory: createFrame()")
    return m


@pytest.fixture
def tmp_cfg(tmp_path: Path):
    """저장소의 config/prompts 를 그대로 쓰되 출력은 tmp 로 보내는 Config."""
    import shutil

    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "prompts", root / "prompts")
    shutil.copytree(ROOT / "templates", root / "templates")
    shutil.copytree(ROOT / "style", root / "style")
    (root / "sdd.yaml").write_text(
        "source:\n  root: ./hal\n  compile_commands: ./hal/compile_commands.json\n"
        "output:\n  facts_dir: build/facts\n  sdd_dir: sdd\n  diagrams_dir: sdd/diagrams\n"
        "agent:\n  kind: dry-run\n  max_input_chars: 4000\n"
        "review:\n  require_citations: true\n  max_retries: 1\n",
        encoding="utf-8")
    (root / "hal").mkdir()
    cfg = load(root / "sdd.yaml")
    # Legacy transport tests supply synthetic HTTP responses; no model call is made.
    cfg.agent.allow_direct_api = True
    return cfg
