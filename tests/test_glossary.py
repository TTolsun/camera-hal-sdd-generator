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
    # 한 줄로 접힌 목록. 제목 줄에 이름이 처음 나온 차례로 보이고, 목차에는 넣지 않는다.
    assert '<details class="page-terms">' in doc
    assert "<summary>이 문서의 용어: 파이프라인 핸들러, IPA</summary>" in doc
    assert 'id="이-문서의-용어"' not in doc
    assert 'href="glossary.html"' in doc
    import re
    assert re.search(r'"terms": "[0-9a-f]{10}"', doc)  # 용어 자료 주소의 해시
    nested = (out / "nested/detail.html").read_text(encoding="utf-8")
    assert "이 문서의 용어" not in nested
    page = (out / "glossary.html").read_text(encoding="utf-8")
    assert "화질 알고리즘 모듈입니다." in page and "장치별 처리 구성 요소입니다." in page
    assert '"terms"' not in page
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


def test_용어_목록은_한_줄로_접고_앞의_이름만_보인다():
    terms = [glossary.Term(f"T{i}", "뜻입니다.") for i in range(glossary.SHOWN + 2)]
    text = glossary.block(terms, "glossary.md")
    assert text.startswith('??? page-terms "이 문서의 용어: T0, T1, T2, T3 외 2개"\n')
    assert f"    - **T{glossary.SHOWN + 1}**: 뜻입니다." in text
    assert "외" not in glossary.block(terms[:glossary.SHOWN], "glossary.md").splitlines()[0]


def test_용어집은_묶음_바로가기와_용어별_주소를_가진다(tmp_cfg, sample_model):
    import json
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, GLOSSARY.replace("common:", "  - {term: 3A, definition: 세 알고리즘입니다.}\n"
                                             "  - {term: bayer, definition: 색 배열입니다.}\ncommon:"))
    add_prose(tmp_cfg, "IPA를 씁니다.")
    out = export_site(tmp_cfg)
    page = (out / "glossary.html").read_text(encoding="utf-8")
    # 바로가기는 숫자, 영문, 한글 순서로 각 묶음의 첫 용어를 가리킨다. 묶음 제목은 따로 두지 않는다.
    assert ('<a href="#term-3a">0–9</a> · <a href="#term-bayer">B</a> · <a href="#term-ipa">I</a>'
            ' · <a href="#term-파이프라인-핸들러">ㅍ</a>' in page)
    assert "<h2" not in page.split("<article>")[1].split("</article>")[0]
    assert '<strong id="term-ipa">IPA</strong>' in page
    assert '<strong id="term-파이프라인-핸들러">' in page
    search = json.loads((out / "assets/search.json").read_text(encoding="utf-8"))
    assert {"title": "IPA (Image Processing Algorithms)", "page": "용어집",
            "url": "glossary.html#term-ipa"} in search
    data = json.loads((out / "assets/glossary.json").read_text(encoding="utf-8"))
    assert {"id": "term-파이프라인-핸들러", "term": "파이프라인 핸들러",
            "names": ["파이프라인 핸들러", "Pipeline Handler"], "definition": "장치별 처리 구성 요소입니다."} in data


def test_용어집_주소가_겹치면_실패한다(tmp_cfg):
    write_glossary(tmp_cfg, "terms:\n  - {term: IPA, definition: 가}\n  - {term: ipa, definition: 나}\n")
    with pytest.raises(RuntimeError, match="주소"):
        glossary.load(tmp_cfg)


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


def test_영어판_뜻_상자_자료도_번역한다(tmp_cfg, sample_model):
    import json
    import re
    from sdd.site_localization import display_strings, source_hash
    prepare(tmp_cfg, sample_model)
    write_glossary(tmp_cfg, GLOSSARY)
    add_prose(tmp_cfg, "IPA를 씁니다.")
    out = export_site(tmp_cfg)
    pages, units = {}, set()
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        pages[path.relative_to(out).as_posix()] = source_hash(text)
        units.update(display_strings(text))
    for entry in json.loads((out / "assets/search.json").read_text(encoding="utf-8")):
        units.update(entry[k] for k in ("title", "page") if re.search("[가-힣]", entry[k]))
    for item in json.loads((out / "assets/glossary.json").read_text(encoding="utf-8")):
        units.update(v for v in [item["term"], item["definition"], *item["names"]] if re.search("[가-힣]", v))
    strings = {s: "English " + " ".join(re.findall(r"\{\{\d+\}\}", s)) for s in units}
    (tmp_cfg.root / "english.json").write_text(json.dumps({"schema": 1, "pages": pages, "strings": strings}),
                                               encoding="utf-8")
    tmp_cfg.raw["site"]["english_catalog"] = "english.json"
    out = export_site(tmp_cfg)
    data = json.loads((out / "en/assets/glossary.json").read_text(encoding="utf-8"))
    # 주소(id)는 한국어 용어집과 같아야 하므로 번역하지 않는다.
    assert all(not re.search("[가-힣]", json.dumps({**item, "id": ""}, ensure_ascii=False)) for item in data)
    assert any(item["term"] == "IPA" for item in data)
    ko = re.search(r'"terms": "([0-9a-f]+)"', (out / "device.html").read_text(encoding="utf-8"))[1]
    en = re.search(r'"terms": "([0-9a-f]+)"', (out / "en/device.html").read_text(encoding="utf-8"))[1]
    assert ko != en  # 영어판은 번역한 자료의 해시를 쓴다
    # 두 용어가 같은 영어 이름으로 번역되면 영어 뜻 상자가 틀린 뜻을 보이므로 게시를 멈춘다.
    catalog = json.loads((tmp_cfg.root / "english.json").read_text(encoding="utf-8"))
    catalog["strings"]["파이프라인 핸들러"] = "IPA"
    (tmp_cfg.root / "english.json").write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(RuntimeError, match="shared by two terms"):
        export_site(tmp_cfg)
