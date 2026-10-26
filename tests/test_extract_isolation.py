"""실제 Clang 추출을 번갈아 실행해 루트·제외 규칙이 섞이지 않는지 확인한다."""

from dataclasses import replace

import pytest

from sdd.facts import callgraph, comments, docblocks
from sdd.facts.model import ClassInfo, KnowledgeModel


@pytest.fixture
def source_cases(tmp_path, tmp_cfg):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "shared.h").write_text(
        "class Base {};\nstruct Payload {};\ninline void helper() {}\n", encoding="utf-8")
    (first / "blocked.h").write_text("class Blocked {};\n", encoding="utf-8")
    (first / "unit.cpp").write_text(
        '#include "shared.h"\n#include "blocked.h"\n'
        "class Active : public Base { Payload field; };\n"
        "void active() { helper(); }\n", encoding="utf-8")
    # 같은 헤더가 첫 실행에서는 루트 안이고 다음 실행에서는 루트 밖이다.
    (second / "unit.cpp").write_text(
        '#include "../first/shared.h"\nclass Other {};\n'
        "void other() { helper(); }\n", encoding="utf-8")

    def case(root, excludes, classes, functions):
        cfg = replace(tmp_cfg, source_root=root, exclude=excludes)
        entries = [{"directory": str(root), "file": str(root / "unit.cpp"),
                    "arguments": ["clang++", "-std=c++17", str(root / "unit.cpp")]}]
        return cfg, entries, set(classes.split()), set(functions.split())

    return [
        case(first, ["blocked.h"], "Base Payload Active", "helper active"),
        case(first, [], "Base Payload Active Blocked", "helper active"),
        case(second, [], "Other", "other"),
        case(first, ["shared.h"], "Blocked Active", "active"),
    ]


def check_comments(case):
    cfg, entries, classes, functions = case
    model = KnowledgeModel()
    stats = comments.collect(model, cfg, entries)
    assert stats["errors"] == 0
    assert set(model.classes) == classes
    assert set(model.functions) == functions


def check_callgraph(case):
    cfg, entries, classes, functions = case
    graph = callgraph.build_graph(cfg, entries)
    assert {qualified for _, qualified in graph.classes.values()} == classes
    assert {fd.qualified for fd in graph.defs.values()} == functions
    # 제외된 선언을 관계·호출 대상으로도 다시 들이지 않는다.
    assert graph.inherits == ([("Active", "Base")] if "Active" in classes and "Base" in classes else [])
    assert graph.fields == ([("Active", "Payload", "field")]
                            if "Active" in classes and "Payload" in classes else [])
    caller = next(fd for fd in graph.defs.values() if fd.qualified in {"active", "other"})
    assert [call.callee_name for call in caller.calls] == (["helper"] if "helper" in functions else [])


@pytest.mark.parametrize("check", [check_comments, check_callgraph])
def test_direct_collectors_isolate_roots_and_excludes(source_cases, check):
    # 캐시에 있던 같은 파일을 다른 root/exclude로 판정하고, 다시 처음 설정으로 돌아간다.
    for index in [0, 1, 2, 3, 2, 0]:
        check(source_cases[index])


def test_comments_and_callgraph_can_interleave(source_cases, monkeypatch):
    original = comments.parse_args
    nested = False

    def parse_with_other_extraction(entry):
        nonlocal nested
        if not nested:
            nested = True
            check_callgraph(source_cases[2])
            check_callgraph(source_cases[1])
            check_comments(source_cases[3])
        return original(entry)

    # 첫 comments 호출이 만든 범위 상태는 중첩 추출이 끝난 뒤에도 그대로여야 한다.
    monkeypatch.setattr(comments, "parse_args", parse_with_other_extraction)
    check_comments(source_cases[0])
    assert nested
    check_callgraph(source_cases[0])


def test_docblocks_use_their_own_excludes(tmp_cfg):
    source = tmp_cfg.source_root / "unit.cpp"
    source.write_text("/** \\class Camera\n * \\brief Camera device\n */\n", encoding="utf-8")
    entries = [{"directory": str(tmp_cfg.source_root), "file": str(source)}]
    for excludes, expected in [(["unit.cpp"], ""), ([], "Camera device"), (["unit.cpp"], "")]:
        cfg = replace(tmp_cfg, exclude=excludes)
        model = KnowledgeModel(classes={"Camera": ClassInfo(name="Camera")})
        docblocks.collect(model, cfg, entries)
        assert model.classes["Camera"].brief == expected
