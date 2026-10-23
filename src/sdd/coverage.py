"""Pure scope analysis over supplied facts, selectors and evidence; no filesystem access."""

from __future__ import annotations

from .facts.model import KnowledgeModel
from .matching import is_anonymous, match_any, matches_symbol


def _select_sections(kind: str, name: str, snapshot: KnowledgeModel, sections: list[dict]) -> set[str]:
    selected = set()
    for section in sections:
        section_kind = section.get("kind", "prose")
        facts = section.get("facts", {})
        if kind == "class" and section_kind in ("prose", "per-package"):
            if not matches_symbol(name, facts.get("classes") or []):
                continue
            if section_kind == "per-package" and not any(name in p.classes for p in snapshot.packages.values()):
                continue
        elif kind == "function" and section_kind == "prose":
            if not matches_symbol(name, facts.get("functions") or []):
                continue
        else:
            continue
        selected.add(section["id"])
    return selected


def audit(model: KnowledgeModel, files: list[str],
          base_model: KnowledgeModel | None = None, *, sections: list[dict], excluded: list[str],
          manual_evidence: dict[str, list[str]], impacted_sections: set[str],
          non_semantic: dict[str, str] | None = None) -> dict:
    """non_semantic: 주석·공백·#include 만 바뀐 파일과 그 이유 (change_kind.classify 결과).

    그 파일들에만 걸린 항목은 검토 항목(findings)이 아니라 자동 분류(classified)로 남긴다.
    """
    non_semantic = non_semantic or {}
    ignored = sorted(f for f in set(files) if match_any(f, excluded))
    active = set(files) - set(ignored)
    # Inspect both sides so deleted declarations and renamed paths cannot disappear.
    entities: dict[tuple[str, str], dict] = {}
    for side, snapshot in [("base", base_model), ("head", model)]:
        if snapshot is None:
            continue
        for kind, collection in [("class", snapshot.classes), ("function", snapshot.functions)]:
            for name, entity in collection.items():
                # 익명 구조체는 어떤 문서 설정으로도 선택할 수 없으므로 "선택하는 문서가 없다" 는
                # 보고가 영구적으로 남는다. 그 구조체를 담은 바깥 클래스가 같은 파일을 이미 다룬다.
                if kind == "class" and is_anonymous(name):
                    continue
                if kind == "class":
                    locations = [entity.loc] + [loc for method in entity.methods for loc in (method.loc, method.def_loc)]
                else:
                    locations = [entity.loc, entity.def_loc]
                locations = [loc for loc in locations if loc and loc.file in active]
                if not locations:
                    continue
                item = entities.setdefault((kind, name), {"kind": kind, "name": name, "files": set(),
                                                          "evidence": {}, "sections": set()})
                item["files"].update(loc.file for loc in locations)
                item["evidence"][side] = sorted({loc.cite() for loc in locations})
                item["sections"].update(_select_sections(kind, name, snapshot, sections))

    items = []
    findings = []
    classified = []
    for key in sorted(entities):
        item = entities[key]
        item["files"] = sorted(item["files"])
        item["sections"] = sorted(item["sections"])
        reason = ("entity-outside-document-scope" if not item["sections"] else
                  "document-not-scheduled" if not impacted_sections.intersection(item["sections"]) else None)
        if reason and all(f in non_semantic for f in item["files"]):
            item["status"] = "non-semantic"
            classified.append({"reason": reason, "kind": item["kind"], "name": item["name"],
                               "files": item["files"], "classification": non_semantic[item["files"][0]]})
            items.append(item)
            continue
        item["status"] = "needs-review" if reason else "mapped"
        items.append(item)
        if reason:
            findings.append({"reason": reason, "kind": item["kind"],
                             "name": item["name"], "files": item["files"]})

    file_items = []
    for file in sorted(active):
        watch = sorted(s["id"] for s in sections if match_any(file, s.get("watch") or []))
        manual = sorted(s["id"] for s in sections if s.get("kind") == "manual"
                        and file in manual_evidence.get(s["id"], []))
        related = [item for item in items if file in item["files"]]
        if file in non_semantic:
            if not related:
                classified.append({"reason": "no-extracted-entity", "kind": "file", "name": file,
                                   "files": [file], "classification": non_semantic[file]})
            file_items.append({"file": file, "watch_sections": watch, "manual_review_sections": manual,
                               "status": "non-semantic"})
            continue
        if not related:
            # Build scripts, unparsed sources and deleted files without baseline facts
            # require review even when a broad watch rule selects a document.
            findings.append({"reason": "no-extracted-entity", "kind": "file", "name": file, "files": [file]})
        file_items.append({"file": file, "watch_sections": watch, "manual_review_sections": manual,
                           "status": "needs-review" if not related or any(i["status"] == "needs-review" for i in related) else "mapped"})
    return {"schema": 1, "status": "needs-review" if findings else "mapped",
            "baseline_available": base_model is not None, "ignored_files": ignored,
            "files": file_items, "entities": items, "findings": findings, "classified": classified,
            "limitations": ["File-level scope mapping does not prove changed-line coverage, generated prose accuracy or human approval.",
                            "Without baseline facts, removed entities in surviving files may be missed.",
                            "A watch hit, package summary or scenario call is not class/function documentation coverage.",
                            "Comment, whitespace and #include-only changes are classified without review; "
                            "an #include can still change preprocessing elsewhere."]}
