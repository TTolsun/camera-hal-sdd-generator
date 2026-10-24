"""설계 근거가 파일 전체를 현재 해시로 고정한 비코드 파일은 다시 만드는 문서가 다루는 변경으로 분류한다."""

import subprocess

import yaml

from sdd.evidence import collect
from sdd.facts.model import KnowledgeModel
from sdd.impact import compute
from sdd.impact_review import review_markdown


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8").strip()


def _commit(root, text):
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "tuning.yaml").write_text(text, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "c")
    return _git(root, "rev-parse", "HEAD")


def _setup(cfg, start, end, sha=None, watch=("data/*.yaml",)):
    source = {"id": "tuning", "file": "data/tuning.yaml", "start": start, "end": end}
    if sha:
        source["sha256"] = sha
    sec = {"id": "ipa", "watch": list(watch), "design_topics": [{"id": "t", "sources": [source]}]}
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [sec]}), encoding="utf-8")


def _model(cfg, sha):
    m = KnowledgeModel(meta={"source_commit": sha})
    collect(cfg, m)
    return m


TEXT = "# header\nalgorithms:\n  - Agc:\n...\n"


def test_파일_전체를_현재_해시로_고정한_근거는_변경을_자동_분류한다(tmp_cfg):
    root = tmp_cfg.source_root
    _git(root, "init", "-q")
    head = _commit(root, TEXT)
    _setup(tmp_cfg, "# header", "...")
    pinned_sha = _model(tmp_cfg, head).evidence["ipa/t/tuning"]["sha256"]
    _setup(tmp_cfg, "# header", "...", pinned_sha)
    model = _model(tmp_cfg, head)
    assert model.evidence["ipa/t/tuning"]["whole_file"] is True
    report = compute(tmp_cfg, model, ["data/tuning.yaml"], "a", head, KnowledgeModel(), non_semantic={})
    assert report.coverage["findings"] == []
    assert [(c["name"], c["classification"], c["sections"]) for c in report.coverage["classified"]] == [
        ("data/tuning.yaml", "pinned-design-evidence", ["ipa"])]
    assert "설계 근거가 파일 전체를 고정함" in review_markdown(report)


def test_범위_검사용_표시는_원고_지문을_바꾸지_않는다(tmp_cfg):
    from sdd.evidence import fingerprint
    root = tmp_cfg.source_root
    _git(root, "init", "-q")
    head = _commit(root, TEXT)
    _setup(tmp_cfg, "# header", "...")
    model = _model(tmp_cfg, head)
    sec = tmp_cfg.sections()[0]
    before = fingerprint(model, sec)
    del model.evidence["ipa/t/tuning"]["whole_file"]       # 이 표시가 없던 생성기로 만든 원고
    assert fingerprint(model, sec) == before


def test_일부만_발췌했거나_해시가_없거나_어긋나거나_문서를_다시_만들지_않으면_검토로_남긴다(tmp_cfg):
    root = tmp_cfg.source_root
    _git(root, "init", "-q")
    head = _commit(root, TEXT)

    def findings(start, end, sha=None, watch=("data/*.yaml",)):
        _setup(tmp_cfg, start, end, sha, watch)
        report = compute(tmp_cfg, _model(tmp_cfg, head), ["data/tuning.yaml"], "a", head, KnowledgeModel(),
                         non_semantic={})
        return [f["name"] for f in report.coverage["findings"]]

    _setup(tmp_cfg, "algorithms:", "Agc:")
    partial_sha = _model(tmp_cfg, head).evidence["ipa/t/tuning"]["sha256"]
    assert findings("algorithms:", "Agc:", partial_sha) == ["data/tuning.yaml"]       # 발췌 밖 변경을 다루지 못함
    assert findings("# header", "...") == ["data/tuning.yaml"]                         # 해시로 고정하지 않음
    assert findings("# header", "...", "0" * 64) == ["data/tuning.yaml"]               # 고정한 내용과 다름
    _setup(tmp_cfg, "# header", "...")
    whole_sha = _model(tmp_cfg, head).evidence["ipa/t/tuning"]["sha256"]
    assert findings("# header", "...", whole_sha, watch=()) == ["data/tuning.yaml"]     # 문서를 다시 만들지 않음
