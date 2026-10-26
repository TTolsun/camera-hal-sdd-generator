"""선언에 붙지 않은 문서 주석 블록을 클래스에 연결하는 규칙."""

from pathlib import Path

from sdd.facts import docblocks

NL = chr(10)
from sdd.facts.model import ClassInfo, KnowledgeModel, Location

DOC = """
/**
 * \\file
 * \\brief 파일 설명은 클래스가 아니므로 대상이 아니다
 */

/**
 * \\class Camera
 * \\brief Camera device
 *
 * 본문은 가져오지 않는다.
 */

/**
 * \\struct Request
 * \\brief A frame capture request
 */

/**
 * \\class Nowhere
 * \\brief 사실에 없는 이름
 */
"""


def _model():
    return KnowledgeModel(classes={
        "hal::Camera": ClassInfo("hal::Camera", Location("device/camera.h", 10)),
        "hal::Request": ClassInfo("hal::Request", Location("device/request.h", 5)),
    })


def test_이름이_하나로_정해지면_설명을_채운다():
    model = _model()
    for name, brief in docblocks.blocks(DOC):
        target = docblocks.resolve(name, model)
        if target:
            model.classes[target].brief = brief
    assert model.classes["hal::Camera"].brief == "Camera device"
    assert model.classes["hal::Request"].brief == "A frame capture request"


def test_파일_설명과_사실에_없는_이름은_대상이_아니다():
    model = _model()
    names = [n for n, _ in docblocks.blocks(DOC)]
    assert "Nowhere" in names                      # 블록으로는 읽되
    assert docblocks.resolve("Nowhere", model) is None   # 연결하지는 않는다
    assert not any(n == "file" for n in names)     # \file 은 대상 태그가 아니다


def test_같은_짧은_이름은_같은_디렉터리로_가린다():
    """구현 파일은 자기 옆에 선언된 것을 설명한다."""
    model = KnowledgeModel(classes={
        "hal::ipu3::Context": ClassInfo("hal::ipu3::Context", Location("ipa/ipu3/context.h", 9)),
        "hal::rkisp1::Context": ClassInfo("hal::rkisp1::Context", Location("ipa/rkisp1/context.h", 9)),
    })
    assert docblocks.resolve("Context", model) is None                      # 단서가 없으면 비운다
    assert docblocks.resolve("Context", model, near="ipa/ipu3") == "hal::ipu3::Context"
    assert docblocks.resolve("Context", model, near="ipa/rkisp1") == "hal::rkisp1::Context"
    assert docblocks.resolve("Context", model, near="ipa/uvc") is None      # 어느 쪽도 아니면 비운다


def test_한정_이름은_그대로_찾는다():
    model = _model()
    assert docblocks.resolve("hal::Camera", model) == "hal::Camera"


def test_한정_이름의_앞부분까지_후보의_꼬리와_대조한다():
    """중첩 클래스의 멤버 구조체는 마지막 마디만 보면 겹치지만, 적힌 한정 이름으로 갈린다."""
    model = KnowledgeModel(classes={
        "ipa::AgcMeanLuminance::Params": ClassInfo("ipa::AgcMeanLuminance::Params",
                                                   Location("libipa/agc_mean_luminance.h", 30)),
        "ipa::AgcMSV::Params": ClassInfo("ipa::AgcMSV::Params", Location("libipa/agc_msv.h", 20)),
    })
    assert docblocks.resolve("Params", model) is None
    assert docblocks.resolve("AgcMeanLuminance::Params", model) == "ipa::AgcMeanLuminance::Params"
    assert docblocks.resolve("AgcMSV::Params", model) == "ipa::AgcMSV::Params"
    assert docblocks.resolve("Other::Params", model) is None       # 어느 꼬리와도 안 맞으면 비운다


def test_파일의_네임스페이스_선언으로_후보를_좁힌다():
    model = KnowledgeModel(classes={
        "ipa::agc::ActiveState": ClassInfo("ipa::agc::ActiveState", Location("libipa/agc.h", 12)),
        "ipa::awb::ActiveState": ClassInfo("ipa::awb::ActiveState", Location("libipa/awb.h", 12)),
    })
    assert docblocks.resolve("ActiveState", model) is None
    assert docblocks.resolve("ActiveState", model,
                             namespaces=frozenset({"ipa", "agc"})) == "ipa::agc::ActiveState"
    # 두 네임스페이스가 모두 선언된 파일에서는 하나로 좁혀지지 않으므로 비운다.
    assert docblocks.resolve("ActiveState", model,
                             namespaces=frozenset({"ipa", "agc", "awb"})) is None


def test_using_namespace_와_별칭은_선언으로_치지_않는다():
    text = NL.join([
        "using namespace foreign;",
        "namespace alias_name = libcamera::ipa::agc;",
        "namespace ipa::agc {",
        "inline namespace v1 {",
        "} }",
    ])
    assert docblocks.file_namespaces(text) == frozenset({"ipa", "agc", "v1"})


def test_선언에_붙은_주석을_덮어쓰지_않는다(tmp_path, tmp_cfg):
    src = tmp_path / "src"
    (src / "device").mkdir(parents=True)
    (src / "device" / "camera.cpp").write_text(DOC, encoding="utf-8")
    tmp_cfg.source_root = src
    model = _model()
    model.classes["hal::Camera"].brief = "헤더에 적힌 설명"
    entries = [{"file": str(src / "device" / "camera.cpp"), "directory": str(src)}]
    stats = docblocks.collect(model, tmp_cfg, entries)
    assert model.classes["hal::Camera"].brief == "헤더에 적힌 설명"
    assert model.classes["hal::Request"].brief == "A frame capture request"
    assert stats["filled"] == 1
    assert stats["unknown"] == 1                   # Nowhere


def test_제외한_경로는_읽지_않는다(tmp_path, tmp_cfg):
    src = tmp_path / "src"
    (src / "third_party").mkdir(parents=True)
    (src / "third_party" / "camera.cpp").write_text(DOC, encoding="utf-8")
    tmp_cfg.source_root = src
    tmp_cfg.exclude = ["third_party/**"]
    model = _model()
    entries = [{"file": str(src / "third_party" / "camera.cpp"), "directory": str(src)}]
    stats = docblocks.collect(model, tmp_cfg, entries)
    assert stats["files"] == 0 and stats["filled"] == 0
    assert model.classes["hal::Camera"].brief == ""


def test_멤버_설명을_클래스_설명으로_붙이지_않는다():
    """한 블록이 클래스와 멤버를 함께 설명할 때, 클래스에 자기 설명이 없으면 비운다."""
    doc = NL.join([
        "/**",
        " * BSclass Ctx",
        " *",
        " * BSfn Ctx::Ctx",
        " * BSbrief 생성자 설명",
        " */",
    ]).replace("BS", chr(92))
    assert docblocks.blocks(doc) == []


def test_대상_태그의_설명만_읽는다():
    doc = NL.join([
        "/**",
        " * BSstruct Ctx",
        " * BSbrief 문맥 구조체",
        " *",
        " * BSvar Ctx::frames",
        " * BSbrief 프레임 고리 버퍼",
        " */",
    ]).replace("BS", chr(92))
    assert docblocks.blocks(doc) == [("Ctx", "문맥 구조체")]