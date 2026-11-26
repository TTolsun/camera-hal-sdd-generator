"""커밋 메시지를 설계 근거로 고정하고, 소스 발췌를 바꾼 커밋에서 근거 후보를 찾는다."""

import json
import subprocess

import yaml

from sdd import history_candidates
from sdd.cli import main
from sdd.contract_schema import configuration_errors
from sdd.evidence import collect, topic_blocks
from sdd.facts.model import KnowledgeModel
from sdd.site_markdown import _render
from sdd.validate import extract_citations

WHY = """Add frame queue with bounded depth

The sensor driver drops frames when more than four buffers are queued,
so the queue rejects requests beyond that depth instead of blocking.

Change-Id: I0123456789abcdef0123456789abcdef01234567
Signed-off-by: T <t@example.invalid>
"""

CODE = """#include "queue.h"

int Queue::push(Request *r)
{
\tif (depth_ >= 4)
\t\treturn -EBUSY;
\titems_.push_back(r);
\treturn 0;
}
"""


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8").strip()


def _commit(root, files, message):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false",
         "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _sections(cfg, sources, question="큐가 요청을 거절하는 조건과 이유는 무엇입니까?"):
    sec = {"id": "queue", "design_topics": [{"id": "depth", "question": question, "sources": sources}]}
    cfg.sections_file.write_text(yaml.safe_dump({"sections": [sec]}, allow_unicode=True), encoding="utf-8")


def _model(cfg, head):
    model = KnowledgeModel(meta={"source_commit": head})
    collect(cfg, model)
    return model


def _repo(cfg):
    root = cfg.source_root
    _git(root, "init", "-q")
    first = _commit(root, {"src/queue.cpp": CODE}, WHY)
    head = _commit(root, {"README": "x\n"}, "Add readme")
    return root, first, head


WHY_SOURCE = {"id": "why", "kind": "commit", "start": "Add frame queue", "end": "instead of blocking."}


def test_커밋_메시지_구간을_불변_근거로_고정하고_인용을_허용한다(tmp_cfg):
    _, first, head = _repo(tmp_cfg)
    _sections(tmp_cfg, [{**WHY_SOURCE, "revision": first}])
    model = _model(tmp_cfg, head)
    record = model.evidence["queue/depth/why"]
    assert record["status"] == "available", record
    assert record["origin"] == "commit-message" and record["commit"] == head and record["revision"] == first
    assert record["file"] == f"@commit/{first[:12]}.txt" and record["line"] == 1 and record["end_line"] == 4
    assert record["text"].endswith("instead of blocking.") and "Change-Id" not in record["text"]
    assert record["change_id"] == "I0123456789abcdef0123456789abcdef01234567"
    assert record["whole_file"] is False
    cite = f"{record['file']}:1"
    assert cite in model.citations()
    assert extract_citations(f"깊이를 넷으로 제한했습니다 `{cite}`.") == [cite]


def test_현재_이력에_없는_커밋과_바뀐_본문은_검토_대상으로_남긴다(tmp_cfg):
    root, first, head = _repo(tmp_cfg)
    _git(root, "checkout", "-q", "-b", "side", first)
    side = _commit(root, {"side.txt": "s\n"}, "Side change\n\nNot merged into the facts commit.")
    _git(root, "checkout", "-q", "-")
    _sections(tmp_cfg, [{**WHY_SOURCE, "id": "side", "revision": side, "start": "Side change", "end": "facts commit."},
                        {**WHY_SOURCE, "id": "stale", "revision": first, "sha256": "0" * 64},
                        {**WHY_SOURCE, "id": "missing", "revision": "f" * 40}])
    model = _model(tmp_cfg, head)
    assert model.evidence["queue/depth/side"]["status"] == "needs-review"
    assert "이력에 없습니다" in model.evidence["queue/depth/side"]["reason"]
    assert "재검토" in model.evidence["queue/depth/stale"]["reason"]
    assert model.evidence["queue/depth/missing"]["status"] == "needs-review"
    assert not any(c.startswith("@commit/") for c in model.citations() if "stale" in c)
    blocks, gaps = topic_blocks(model, "queue", tmp_cfg.sections()[0]["design_topics"][0])
    assert blocks == [] and len(gaps) == 3


def test_커밋_근거_설정은_해시와_앵커만_받는다():
    def errors(source):
        return configuration_errors({"id": "s", "design_topics": [{"id": "t", "sources": [source]}]})
    good = {**WHY_SOURCE, "revision": "a" * 40}
    assert errors(good) == []
    assert any("revision" in e for e in errors({**WHY_SOURCE, "revision": "abc123"}))
    assert any("file" in e for e in errors({**good, "file": "src/queue.cpp"}))
    assert any("scope" in e for e in errors({**good, "scope": {"start": "a", "end": "b"}}))
    assert any("end" in e for e in errors({**good, "end": ""}))


def test_모델_입력과_원문_상세는_당시_의도임을_표시하고_코드_링크를_만들지_않는다(tmp_cfg):
    _, first, head = _repo(tmp_cfg)
    _sections(tmp_cfg, [{**WHY_SOURCE, "revision": first}])
    model = _model(tmp_cfg, head)
    blocks, gaps = topic_blocks(model, "queue", tmp_cfg.sections()[0]["design_topics"][0])
    assert gaps == [] and "현재 동작의 근거가 아닙니다" in blocks[0].text
    from sdd.contract_render import _source_detail
    detail = _source_detail(model.evidence["queue/depth/why"], "why")
    assert '커밋 기록' in detail and first in detail and "I0123456789abcdef" in detail
    record = model.evidence["queue/depth/why"]
    rendered, _, _ = _render(f"이유입니다 `{record['file']}:1`.", "a.md", set(), model, "https://host/repo", head)
    assert "/blob/" not in rendered and "https://host" not in rendered


def test_영어판은_커밋_기록_제목을_고정_번역한다():
    from sdd.translation import fixed_translation
    assert fixed_translation("커밋 기록: @commit/1a2b3c4d5e6f.txt:1") == "Commit record: @commit/1a2b3c4d5e6f.txt:1"


def _moved_history(cfg):
    root = cfg.source_root
    _git(root, "init", "-q")
    first = _commit(root, {"src/queue.cpp": CODE}, WHY)
    moved = _commit(root, {"src/request_queue.cpp": CODE}, "Rename queue source file")
    (root / "src/queue.cpp").unlink()
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-q", "--amend", "--no-edit")
    moved = _git(root, "rev-parse", "HEAD")
    fixed = _commit(root, {"src/request_queue.cpp": CODE.replace("return -EBUSY;", "return -EBUSY; /* full */")},
                    "Fix typo")
    return first, moved, fixed


def test_파일_이동_뒤에도_줄의_원래_도입_커밋을_후보로_찾는다(tmp_cfg):
    first, moved, head = _moved_history(tmp_cfg)
    _sections(tmp_cfg, [{"id": "guard", "file": "src/request_queue.cpp",
                         "start": "\tif (depth_ >= 4)", "end": "\titems_.push_back(r);"}])
    model = _model(tmp_cfg, head)
    report = history_candidates.collect(tmp_cfg, model)
    excerpt = report["topics"][0]["excerpts"][0]
    by_revision = {c["revision"]: c for c in excerpt["candidates"]}
    assert first in by_revision, excerpt
    origin = by_revision[first]
    assert any("원래 파일: src/queue.cpp" in role for role in origin["roles"])
    assert origin["change_id"] == "I0123456789abcdef0123456789abcdef01234567"
    assert origin["anchors"] == {"start": "Add frame queue with bounded depth", "end": "so the queue rejects requests beyond that depth instead of blocking."}
    typo = by_revision[head]
    assert "범위 최근 변경" in typo["roles"] and typo["later_changes"] == 0
    assert set(typo["signals"]) == {"제목만 있음", "정리성 변경으로 보이는 제목"} and typo["anchors"] is None
    text = history_candidates.markdown(report)
    assert "kind: commit" in text and f"revision: {first}" in text and "Change-Id" in text


def test_후보의_제안_조각을_그대로_등록하면_근거가_된다(tmp_cfg):
    first, _, head = _moved_history(tmp_cfg)
    guard = {"id": "guard", "file": "src/request_queue.cpp", "start": "\tif (depth_ >= 4)", "end": "\titems_.push_back(r);"}
    _sections(tmp_cfg, [guard])
    report = history_candidates.collect(tmp_cfg, _model(tmp_cfg, head))
    candidate = next(c for c in report["topics"][0]["excerpts"][0]["candidates"] if c["revision"] == first)
    snippet = yaml.safe_load(history_candidates._yaml_snippet(candidate))[0]
    _sections(tmp_cfg, [guard, snippet])
    model = _model(tmp_cfg, head)
    assert model.evidence[f"queue/depth/{snippet['id']}"]["status"] == "available"
    again = history_candidates.collect(tmp_cfg, model)
    linked = next(c for c in again["topics"][0]["excerpts"][0]["candidates"] if c["revision"] == first)
    assert linked["already_linked"] is True


def test_명령은_facts와_설정을_바꾸지_않고_후보_파일만_쓴다(tmp_cfg, capsys):
    _, _, head = _moved_history(tmp_cfg)
    _sections(tmp_cfg, [{"id": "guard", "file": "src/request_queue.cpp",
                         "start": "\tif (depth_ >= 4)", "end": "\titems_.push_back(r);"}])
    KnowledgeModel(meta={"source_commit": head}).save(tmp_cfg.facts_path)
    facts = tmp_cfg.facts_path.read_bytes()
    sections = tmp_cfg.sections_file.read_bytes()
    out = tmp_cfg.root / "out"
    assert main(["--config", str(tmp_cfg.root / "sdd.yaml"), "history-candidates", "--out", str(out)]) == 0
    assert tmp_cfg.facts_path.read_bytes() == facts and tmp_cfg.sections_file.read_bytes() == sections
    data = json.loads((out / "history-candidates.json").read_text(encoding="utf-8"))
    assert data["source_commit"] == head and data["topics"][0]["excerpts"][0]["candidates"]
    assert "모델 호출 0회" in capsys.readouterr().out
