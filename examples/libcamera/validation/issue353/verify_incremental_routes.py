"""Map the #348 historical manuscript comparisons to the #353 reader edition."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

from sdd.document_metadata import split_frontmatter


CASES = {
    "move": {
        "commits": ("16a469a1ca3356783940c8362ab7583dfa578e37", "b6f81b756af79bce23240f7bc48032895a3ca2c9"),
        "snapshots": ("move/base-snapshot", "move-final/first-head", "move-final/manuscripts"),
        "repeat_log": "move-final/head-repeat.log",
        "changed_topics": {},
        "changed_figures": set(),
    },
    "device": {
        "commits": ("0d48cb6bb0883f267f9e470057fa7311c52b766c", "0b0f32e7366b2de94983d8cb02d4c32a10b0f561"),
        "snapshots": ("device/base-snapshot", "device/first-head", "device/manuscripts"),
        "repeat_log": "device/head-repeat.log",
        "changed_topics": {"rkisp1-dewarp.md": {"application"}},
        "changed_figures": set(),
    },
    "common": {
        "commits": ("517b863bae2db2dd0c56366119318d6b2fb9ad52", "731a340c8064843075cb9a41e22908eadadbf1bd"),
        "snapshots": ("common-precise/base-verified", "common-precise/first-head", "common-precise/manuscripts"),
        "repeat_log": "common-precise/head-repeat.log",
        "changed_topics": {"request-lifecycle.md": {"stopping"}, "vendor-integration.md": {"shutdown"}},
        "changed_figures": {"request-lifecycle.md"},
    },
}

ROUTES = {
    "request-lifecycle.md": ("정지와-연결-해제를-구분하기", "request-flow.md#stop-and-disconnect"),
    "vendor-integration.md": ("정지와-오류-처리의-책임", "device-integration.md#stop-tests"),
    "rkisp1-dewarp.md": ("스트림-적용과-실행-확인-범위", "implementation.md#rkisp1-dewarp"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def locate_routes(edition: dict) -> dict[str, str]:
    routes = {}
    for source, (fragment, expected) in ROUTES.items():
        matches = [
            f"{page['path']}#{section['id']}"
            for page in edition["pages"]
            for section in page["sections"]
            if section["source"] == source and section.get("fragment") == fragment
        ]
        require(matches == [expected], f"{source}#{fragment} expected {expected}, found {matches}")
        routes[source] = expected
    return routes


def figures(body: str) -> list[str]:
    return re.findall(r"(?ms)^```mermaid[ \t]*\n(.*?)^```$", body)


def citations(body: str) -> list[str]:
    return re.findall(r"(?m)^근거 원문: (.+)$", body)


def compare_manuscript(case: str, source: str, paths: list[Path], rule: dict) -> dict:
    historical = [split_frontmatter(read(path / source)) for path in paths]
    base, head, repeat = [meta for meta, _ in historical]
    base_body, head_body, repeat_body = [body for _, body in historical]
    base_commit, head_commit = rule["commits"]
    label = f"{case}: {source}"
    require([meta["source_commit"] for meta, _ in historical] == [base_commit, head_commit, head_commit],
            f"{label}: unexpected source commit")
    base_topics = base["generated_design"]["answers"]
    head_topics = head["generated_design"]["answers"]
    require(set(base_topics) == set(head_topics), f"{label}: answer inventory changed")
    changed_topics = {topic for topic, answers in base_topics.items() if answers != head_topics[topic]}
    require(changed_topics == rule["changed_topics"].get(source, set()), f"{label}: unexpected changed answers")
    require((figures(base_body) != figures(head_body)) == (source in rule["changed_figures"]),
            f"{label}: unexpected diagram changes")
    require(head_topics == repeat["generated_design"]["answers"] and head_body == repeat_body,
            f"{label}: same-head replay changed answers or manuscript body")
    citations_changed = citations(base_body) != citations(head_body)
    if case == "move":
        require(citations_changed, f"{label}: expected updated citation locations")
    return {
        "changed_topics": sorted(changed_topics),
        "unchanged_topics": sorted(set(base_topics) - changed_topics),
        "changed_figures": source in rule["changed_figures"],
        "citations_changed": citations_changed,
        "repeat_body_sha256": hashlib.sha256(repeat_body.encode("utf-8")).hexdigest(),
    }


def compare(root: Path, edition: dict) -> dict:
    routes = locate_routes(edition)
    reports = {}
    for case, rule in CASES.items():
        paths = [root / directory for directory in rule["snapshots"]]
        require("호출 시도 0회" in read(root / rule["repeat_log"]), f"{case}: repeat did not record zero CLI calls")
        sources = sorted({"request-lifecycle.md", "vendor-integration.md"} | set(rule["changed_topics"]))
        report = {}
        for source in sources:
            result = compare_manuscript(case, source, paths, rule)
            result["canonical"] = routes[source]
            report[source] = result
        reports[case] = {"commits": rule["commits"], "repeat_cli_calls": 0, "manuscripts": report}
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue348_run", type=Path, help="Directory containing the archived #348 snapshots and logs")
    parser.add_argument(
        "--edition",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "config" / "reader-edition.yaml",
    )
    args = parser.parse_args()
    print(json.dumps(compare(args.issue348_run, yaml.safe_load(read(args.edition))), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
