"""NDK-build 가 만든 원본 compile DB 와 legacy HAL3(camera3_*) 진입점으로 끝까지 추출한다.

사내 HAL 의 빌드·인터페이스 전제를 공개 코드만으로 재현한다. 실제 NDK 대신 원본 DB 의 모양
(상대 -I·상대 file·ccache wrapper·-MF/-o)을 그대로 적고, clang 내장 헤더 위치만 가짜로 준다.
"""

import json
import subprocess
from pathlib import Path

import pytest

from sdd import compdb, extract, update
from sdd.config import load
from sdd.facts import callgraph

ROOT = Path(__file__).resolve().parents[1]

HAL3_H = """\
typedef struct camera3_capture_request { int frame_number; } camera3_capture_request_t;
typedef struct camera3_capture_result { int frame_number; } camera3_capture_result_t;
typedef struct camera3_callback_ops {
    void (*process_capture_result)(const struct camera3_callback_ops *, const camera3_capture_result_t *);
} camera3_callback_ops_t;
typedef struct camera3_device { void *priv; } camera3_device_t;
typedef struct camera3_device_ops {
    int (*process_capture_request)(const struct camera3_device *, camera3_capture_request_t *);
    int (*flush)(const struct camera3_device *);
} camera3_device_ops_t;
"""

DEVICE_H = """\
#include "hal3.h"
namespace hal {
class Pipeline {
public:
    int submit(camera3_capture_request_t *request);
    int flush();
};
/** HAL3 device that forwards camera3_device_ops to member functions. */
class CameraDevice {
public:
    int processCaptureRequest(camera3_capture_request_t *request);
    int flush();
    static int sProcessCaptureRequest(const struct camera3_device *dev, camera3_capture_request_t *request);
    static int sFlush(const struct camera3_device *dev);
private:
    Pipeline mPipeline;
    const camera3_callback_ops_t *mCallbacks;
};
}
"""

DEVICE_CPP = """\
#include "CameraDevice.h"
namespace hal {
int CameraDevice::sProcessCaptureRequest(const struct camera3_device *dev, camera3_capture_request_t *request) {
    return static_cast<CameraDevice *>(dev->priv)->processCaptureRequest(request);
}
int CameraDevice::sFlush(const struct camera3_device *dev) {
    return static_cast<CameraDevice *>(dev->priv)->flush();
}
int CameraDevice::processCaptureRequest(camera3_capture_request_t *request) {
    int rc = mPipeline.submit(request);
    camera3_capture_result_t result{request->frame_number};
    mCallbacks->process_capture_result(mCallbacks, &result);
    return rc;
}
int CameraDevice::flush() { return mPipeline.flush(); }
int Pipeline::submit(camera3_capture_request_t *) { return 0; }
int Pipeline::flush() { return 0; }
}
static camera3_device_ops_t sOps = { hal::CameraDevice::sProcessCaptureRequest, hal::CameraDevice::sFlush };
"""

SCENARIOS = """\
defaults:
  depth: 4
scenarios:
  - id: process_capture_request
    title: HAL3 ops 에서 시작하는 캡처 요청
    # 헤더는 const struct camera3_device * 로 적었지만 struct 없이 적어도 같은 정의다.
    from: "hal::CameraDevice::sProcessCaptureRequest(const camera3_device *, camera3_capture_request_t *)"
  - id: flush
    title: 플러시
    from: "CameraDevice::flush()"
"""


def _raw_entry(project: Path) -> dict:
    # ndk-build compile_commands.json 의 실제 모양: LOCAL_PATH 기준 상대 경로, 의존성·출력 플래그, ccache.
    return {
        "directory": str(project),
        "file": "jni/CameraDevice.cpp",
        "command": ("ccache /ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++ -MMD -MP "
                    "-MF obj/local/arm64-v8a/objs/camera/CameraDevice.o.d "
                    "-target aarch64-none-linux-android21 -fdata-sections -ffunction-sections "
                    "-std=c++17 -nostdinc++ -Ijni -DHAL3_LEGACY=1 -c jni/CameraDevice.cpp "
                    "-o obj/local/arm64-v8a/objs/camera/CameraDevice.o"),
    }


@pytest.fixture
def ndk_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    jni = project / "jni"
    jni.mkdir(parents=True)
    (jni / "hal3.h").write_text(HAL3_H, encoding="utf-8")
    (jni / "CameraDevice.h").write_text(DEVICE_H, encoding="utf-8")
    (jni / "CameraDevice.cpp").write_text(DEVICE_CPP, encoding="utf-8")
    (project / "compile_commands.json").write_text(json.dumps([_raw_entry(project)]), encoding="utf-8")
    (tmp_path / "scenarios.yaml").write_text(SCENARIOS, encoding="utf-8")
    (tmp_path / "sdd.yaml").write_text(f"""\
source:
  root: ./project/jni
  compile_commands: ./project/compile_commands.json
  ndk_build:
    enabled: true
    project_dir: ./project
paths:
  sections_file: {ROOT.as_posix()}/config/sections.yaml
  scenarios_file: ./scenarios.yaml
  clang_uml_file: {ROOT.as_posix()}/config/clang-uml.yaml
  prompts: {ROOT.as_posix()}/prompts
  templates: {ROOT.as_posix()}/templates
  style: {ROOT.as_posix()}/style
tools:
  clang_uml: none
agent:
  kind: dry-run
""", encoding="utf-8")
    resource = tmp_path / "ndk-clang-resource"
    (resource / "include").mkdir(parents=True)
    (resource / "include" / "stddef.h").write_text("", encoding="utf-8")
    seen = []

    def fake_resource_dir(clang="clang"):
        seen.append(clang)
        return resource

    monkeypatch.setattr(compdb, "clang_resource_dir", fake_resource_dir)
    return load(tmp_path / "sdd.yaml"), seen, resource


def test_ndk_원본_DB_를_정규화해서_HAL3_시나리오까지_추출한다(ndk_project):
    cfg, seen, resource = ndk_project
    model = extract.run(cfg)

    # 원본 DB 의 컴파일러(ccache 를 뗀 NDK clang)로 내장 헤더 위치를 찾았다.
    assert seen == ["/ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++"]
    argv = compdb.load_entries(cfg.compile_commands)[0]["arguments"]
    assert argv[0].endswith("clang++") and "ccache" not in argv
    assert f"-resource-dir={resource}" in argv
    assert model.meta["comments"]["errors"] == 0
    assert "hal::CameraDevice" in model.classes

    steps = [(m.dst, m.name, m.note) for m in model.scenarios["process_capture_request"].messages]
    # ops 함수 포인터 표의 trampoline 에서 priv 캐스트를 지나 멤버 함수로 이어진다.
    assert steps[0] == ("CameraDevice", "processCaptureRequest", "")
    assert ("Pipeline", "submit", "") in steps
    # framework 로 돌아가는 camera3_callback_ops 호출은 경계로 남긴다.
    assert ("process_capture_result", "함수 포인터, 정적 추적 불가") in [(n, note) for _, n, note in steps]
    assert [m.name for m in model.scenarios["flush"].messages] == ["flush"]


def test_원본_DB_의_상대_include_가_절대_경로가_된다(ndk_project):
    cfg, _, _ = ndk_project
    compdb.ensure(cfg)
    argv = compdb.load_entries(cfg.compile_commands)[0]["arguments"]
    project = cfg.ndk_build["project_dir"]
    assert "-I" + str((Path(project) / "jni").resolve()) in argv
    assert f"-working-directory={Path(project).resolve()}" in argv


def test_같은_이름이_여럿이면_진입점을_임의로_고르지_않는다(ndk_project):
    cfg, _, _ = ndk_project
    entries = compdb.load_entries(compdb.ensure(cfg))
    g = callgraph.build_graph(cfg, entries)

    entry, reason = callgraph.match_entry(g, "flush()")
    assert entry is None and "2개" in reason and "Pipeline" in reason
    entry, reason = callgraph.match_entry(g, "flush")
    assert entry is None and "고를 수 없습니다" in reason
    entry, _ = callgraph.match_entry(g, "hal::Pipeline::flush()")
    assert entry is not None and entry.qualified == "hal::Pipeline::flush"


def test_모호한_진입점은_추출을_중단하고_facts_를_보존한다(ndk_project, tmp_path):
    cfg, _, _ = ndk_project
    extract.run(cfg)
    before = cfg.facts_path.read_bytes()
    (tmp_path / "scenarios.yaml").write_text(SCENARIOS.replace('"CameraDevice::flush()"', '"flush()"'),
                                             encoding="utf-8")
    with pytest.raises(RuntimeError, match="진입점 1개"):
        extract.run(load(tmp_path / "sdd.yaml"))
    assert cfg.facts_path.read_bytes() == before


def test_update_가_ndk_build_로_다시_만든_DB_도_정규화한다(ndk_project, tmp_path, monkeypatch):
    cfg, _, _ = ndk_project
    cfg.raw.setdefault("update", {})["compdb_cmd"] = ["ndk-build", "compile_commands.json"]
    project = Path(cfg.ndk_build["project_dir"])
    calls = []

    def fake_run(cmd, cwd=None, check=False, **kwargs):
        calls.append(cmd)
        (project / "compile_commands.json").write_text(json.dumps([_raw_entry(project)]), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    update._run_compdb_cmd(cfg)
    assert calls == [["ndk-build", "compile_commands.json"]]
    assert compdb.is_normalized(compdb.load_entries(cfg.compile_commands))
