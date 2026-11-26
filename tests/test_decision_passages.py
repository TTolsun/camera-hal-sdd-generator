import subprocess
from types import SimpleNamespace

from sdd.decision_passages import decision_locations


def test_candidates_find_contract_outside_symbol_list_at_nested_source_commit(tmp_path):
    hal = tmp_path / "hal"
    hal.mkdir()
    for file, text in {
        "result.cc": "// A frame marked cancelled contains invalid data.",
        "dispatch.cc": "// A signal argument must remain valid until delivery.",
        "legacy.cc": "// When flush returns, every pending slot has been cancelled.",
        "unbuilt.cc": "// The frame may contain invalid data after stop.",
    }.items():
        (hal / file).write_text(text + "\n", encoding="utf-8")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()
    git("init", "-q")
    git("add", "hal")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "source")
    commit = git("rev-parse", "HEAD")
    (hal / "result.cc").write_text("// different working tree\n", encoding="utf-8")
    cfg = SimpleNamespace(source_root=hal)
    files = ["result.cc", "dispatch.cc", "legacy.cc"]
    section = {"watch_exclude": ["legacy.cc"]}
    cache = {}
    def matches(topic):
        return set(decision_locations(cfg, commit, files, section, {"covers": [topic]}, cache))
    assert matches("completion") == {("result.cc", 1)}
    assert matches("ownership") == {("dispatch.cc", 1)}
