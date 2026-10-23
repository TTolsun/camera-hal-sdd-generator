"""이름 없는 형식·람다 이름에 libclang 이 넣는 절대 경로를 소스 루트 기준으로 바꾸는지 확인한다."""

import os

from sdd.facts.comments import portable_names
from sdd.facts.model import ClassInfo, KnowledgeModel, Location


def test_이름_속_절대_경로를_소스_루트_기준으로_바꾼다(tmp_path):
    root = str(tmp_path / "src")
    inside = os.path.join(root, "ipa", "ctx.h")
    name = f"ns::State::(unnamed struct at {inside}:61:2)"
    lam = f"(lambda at {inside}:7:3)::operator()"
    out = portable_names({name: [lam, "plain at noon"]}, (root,))
    assert out == {"ns::State::(unnamed struct at ipa/ctx.h:61:2)": ["(lambda at ipa/ctx.h:7:3)::operator()", "plain at noon"]}


def test_루트_밖_경로는_싣지_않고_파일마다_다른_이름을_남긴다(tmp_path):
    roots = (str(tmp_path / "src"),)
    a = portable_names(f"(anonymous union at {os.path.join(str(tmp_path), 'usr', 'x.h')}:3:1)", roots)
    b = portable_names(f"(anonymous union at {os.path.join(str(tmp_path), 'opt', 'x.h')}:3:1)", roots)
    assert a.startswith("(anonymous union at x.h#") and a != b
    assert str(tmp_path) not in a + b


def test_evidence_의_발췌는_해시와_맞도록_그대로_둔다(tmp_path):
    raw = f"(unnamed struct at {os.path.join(str(tmp_path), 'a.h')}:1:1)"
    out = portable_names({"evidence": {"q": {"excerpt": raw}}, "classes": {raw: {}}}, (str(tmp_path),))
    assert out["evidence"]["q"]["excerpt"] == raw
    assert list(out["classes"]) == ["(unnamed struct at a.h:1:1)"]


def test_clang_uml_그림을_복사할_때도_경로를_바꾼다(tmp_path):
    from sdd.extract import _copy_mermaid
    src, dst = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    path = os.path.join(str(tmp_path), "a.cpp")
    (src / "c.mmd").write_text(f'c1["A::(unnamed enum at {path}:9:2)"]', encoding="utf-8")
    _copy_mermaid(src, dst, (str(tmp_path),))
    assert (dst / "c.mmd").read_text(encoding="utf-8") == 'c1["A::(unnamed enum at a.cpp:9:2)"]'


def test_모델을_왕복해도_클래스_이름과_위치가_유지된다(tmp_path):
    root = str(tmp_path)
    name = f"A::(unnamed enum at {os.path.join(root, 'a.cpp')}:9:2)"
    model = KnowledgeModel(classes={name: ClassInfo(name, Location("a.cpp", 9))})
    fixed = KnowledgeModel.from_dict(portable_names(model.to_dict(), (root,)))
    assert list(fixed.classes) == ["A::(unnamed enum at a.cpp:9:2)"]
    assert fixed.classes["A::(unnamed enum at a.cpp:9:2)"].name == "A::(unnamed enum at a.cpp:9:2)"
    assert fixed.classes["A::(unnamed enum at a.cpp:9:2)"].loc == Location("a.cpp", 9)
