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


def test_루트_밖_경로는_파일_이름만_남긴다(tmp_path):
    outside = os.path.join(str(tmp_path), "usr", "include", "x.h")
    assert portable_names(f"(anonymous union at {outside}:3:1)", (str(tmp_path / "src"),)) == "(anonymous union at x.h:3:1)"


def test_모델을_왕복해도_클래스_이름과_위치가_유지된다(tmp_path):
    root = str(tmp_path)
    name = f"A::(unnamed enum at {os.path.join(root, 'a.cpp')}:9:2)"
    model = KnowledgeModel(classes={name: ClassInfo(name, Location("a.cpp", 9))})
    fixed = KnowledgeModel.from_dict(portable_names(model.to_dict(), (root,)))
    assert list(fixed.classes) == ["A::(unnamed enum at a.cpp:9:2)"]
    assert fixed.classes["A::(unnamed enum at a.cpp:9:2)"].name == "A::(unnamed enum at a.cpp:9:2)"
    assert fixed.classes["A::(unnamed enum at a.cpp:9:2)"].loc == Location("a.cpp", 9)
