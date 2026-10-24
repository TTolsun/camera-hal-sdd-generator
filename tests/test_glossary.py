"""용어집: 문서마다 쓰인 용어의 뜻을 보여 주고, 뜻이 없는 약어의 게시를 막는다."""

from pathlib import Path

import pytest

from sdd import glossary
from sdd.config import load
from sdd.export_site import export_site
from test_export_site import prepare

ROOT = Path(__file__).resolve().parents[1]


def write_glossary(cfg, text):
    (cfg.config_dir / "glossary.yaml").write_text(text, encoding="utf-8")


GLOSSARY = """terms:
  - term: IPA
    full: Image Processing Algorithms
    definition: 화질 알고리즘 모듈입니다.
  - term: 파이프라인 핸들러
    definition: 장치별 처리 구성 요소입니다.
    aliases: [Pipeline Handler]
common: [API]
"""


def add_prose(cfg, text):
    path = cfg.sdd_dir / "device.md"
    path.write_text(path.read_text(encoding="utf-8").replace("## Evidence", text + "\n\n## Evidence", 1), encoding="utf-8")


def test_문서에_쓰인_용어만_처음_나온_차례로_표에_넣는다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, GLOSSARY)
    add_prose(tmp_cfg, "Pipeline Handler가 IPA를 부릅니다. API도 씁니다.")
    originals = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob("*.md")}
    out = export_site(tmp_cfg)
    doc = (out / "device.html").read_text(encoding="utf-8")
    assert 'id="이-문서의-용어"' in doc
    assert doc.index("파이프라인 핸들러") < doc.index("Image Processing Algorithms")
    assert 'href="glossary.html"' in doc
    nested = (out / "nested/detail.html").read_text(encoding="utf-8")
    assert "이 문서의 용어" not in nested
    page = (out / "glossary.html").read_text(encoding="utf-8")
    assert "화질 알고리즘 모듈입니다." in page and "장치별 처리 구성 요소입니다." in page
    assert 'href="glossary.html"' in (out / "index.html").read_text(encoding="utf-8")
    # 표시용이다. 원고와 Markdown 원문 내려받기는 바뀌지 않는다.
    assert all(p.read_bytes() == original for p, original in originals.items())
    assert (out / "device.md").read_bytes() == originals[tmp_cfg.sdd_dir / "device.md"]


def test_뜻이_없는_약어는_게시를_막고_기존_사이트를_보존한다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, GLOSSARY)
    first = export_site(tmp_cfg)
    before = (first / "device.html").read_bytes()
    add_prose(tmp_cfg, "LSC는 IPU3에서 동작합니다. `ISP` 와 `src/LUT.cpp:1` 은 코드라서 검사하지 않습니다.")
    with pytest.raises(RuntimeError) as error:
        export_site(tmp_cfg)
    assert "IPU3: device.md" in str(error.value) and "LSC: device.md" in str(error.value)
    assert "ISP" not in str(error.value) and "LUT" not in str(error.value)
    assert (first / "device.html").read_bytes() == before


def test_용어집이_없으면_경고만_하고_설정으로_정책을_바꿀_수_있다(tmp_cfg, sample_model, capsys):
    prepare(tmp_cfg, sample_model)
    add_prose(tmp_cfg, "LSC를 씁니다.")
    out = export_site(tmp_cfg)
    assert "LSC: device.md" in capsys.readouterr().out
    assert not (out / "glossary.html").exists()
    tmp_cfg.raw["site"]["undefined_terms"] = "fail"
    with pytest.raises(RuntimeError, match="LSC"):
        export_site(tmp_cfg)
    tmp_cfg.raw["site"]["undefined_terms"] = "always"
    with pytest.raises(RuntimeError, match="undefined_terms"):
        export_site(tmp_cfg)


def test_약어_검사는_코드_발췌와_식별자를_뺀다():
    g = glossary.Glossary([], set(), True)
    text = ("IPA는 모듈입니다. IPAManager 와 V4L2_CID, RGB.\n\n```cpp\nASSERT(x);\n```\n\n"
            "    \tTODO(code);\n\n[링크](HTTP.md) `LSC`\n")
    assert glossary.undefined(g, {"a.md": text}) == {"IPA": ["a.md"], "RGB": ["a.md"]}


def test_먼저_나온_용어는_펼치고_나머지만_접는다():
    terms = [glossary.Term(f"T{i}", "뜻입니다.") for i in range(glossary.OPEN_LIMIT + 2)]
    text = glossary.block(terms, "glossary.md")
    shown, folded = text.split('??? note "나머지 용어 펼치기"')
    assert "- **T0**: " in shown and f"- **T{glossary.OPEN_LIMIT - 1}**: " in shown
    assert f"    - **T{glossary.OPEN_LIMIT}**: " in folded
    assert "???" not in glossary.block(terms[:glossary.OPEN_LIMIT], "glossary.md")


def test_정의는_글자_그대로_보인다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, "terms:\n  - {term: UQ, definition: 'UQ<m, n> 은 *고정* 소수점입니다.'}\n")
    add_prose(tmp_cfg, "UQ를 씁니다.")
    page = (export_site(tmp_cfg) / "glossary.html").read_text(encoding="utf-8")
    assert "UQ&lt;m, n&gt; 은 *고정* 소수점입니다." in page


def test_요약_문단_뒤에_넣는다():
    body = "\n**요약입니다.**\n\n## 본문\n\n내용\n"
    assert glossary.insert(body, "## 용어\n\n").index("## 용어") > body.index("요약")
    assert glossary.insert("## 본문\n", "## 용어\n\n").startswith("## 용어")


@pytest.mark.parametrize("body", ["```cpp\na();\n\nb();\n```\n\n문단\n", "<div>\n\n안\n</div>\n"])
def test_코드나_HTML_블록으로_시작하면_블록을_자르지_않는다(body):
    assert glossary.insert(body, "## 용어\n\n") == "## 용어\n\n" + body


def test_하이픈이_붙은_약어와_하위_목록도_검사한다():
    g = glossary.Glossary([], set(), True)
    text = "LSC-보정을 씁니다. Mali-C55 와 IPA-v2 는 이름입니다.\n\n- 상위\n    - ISP 하위 항목\n"
    assert glossary.undefined(g, {"a.md": text}) == {"ISP": ["a.md"], "LSC": ["a.md"]}


def test_따옴표_없는_off_는_검사를_끈다(tmp_cfg, sample_model):
    import yaml
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, GLOSSARY)
    add_prose(tmp_cfg, "LSC를 씁니다.")
    tmp_cfg.raw["site"]["undefined_terms"] = yaml.safe_load("v: off")["v"]
    assert export_site(tmp_cfg).is_dir()


@pytest.mark.parametrize("text, message", [
    ("terms:\n  - term: IPA\n", "definition"),
    ("terms:\n  - {term: IPA, definition: 가}\n  - {term: B, definition: 나, aliases: [IPA]}\n", "중복"),
    ("terms:\n  - {term: IPA, definition: 가}\ncommon: [IPA]\n", "common"),
])
def test_잘못된_용어집은_실패한다(tmp_cfg, text, message):
    write_glossary(tmp_cfg, text)
    with pytest.raises(RuntimeError, match=message):
        glossary.load(tmp_cfg)


@pytest.mark.parametrize("project", ["examples/libcamera", "examples/inhouse-template"])
def test_예제_용어집은_읽을_수_있고_정의에_뜻없는_약어가_없다(project):
    cfg = load(ROOT / project / "sdd.yaml")
    g = glossary.load(cfg)
    assert g.configured and g.terms
    assert glossary.undefined(g, {"glossary.md": glossary.page(g)}) == {}
