"""Pure scope analysis over supplied facts, selectors and evidence; no filesystem access."""

from __future__ import annotations

from .facts.model import KnowledgeModel
from .matching import is_anonymous, match_any, matches_symbol, package_of, package_selected


def _select_sections(kind: str, name: str, snapshot: KnowledgeModel, sections: list[dict],
                     package_depth: int = 1) -> set[str]:
    selected = set()
    for section in sections:
        section_kind = section.get("kind", "prose")
        facts = section.get("facts", {})
        if kind == "class" and section_kind in ("prose", "per-package"):
            if not matches_symbol(name, facts.get("classes") or []):
                continue
            if section_kind == "per-package":
                # 패키지 문서는 facts.packages 로 고른 패키지의 클래스만 싣는다. 실리지 않는 클래스를
                # 다룬다고 보면 범위 누락이 감춰진다.
                owners = [n for n, p in snapshot.packages.items() if name in p.classes]
                pkg_pats = facts.get("packages") or []
                if not owners or (pkg_pats and not any(package_selected(n, pkg_pats) for n in owners)):
                    continue
        elif kind == "function" and section_kind == "prose":
            if not matches_symbol(name, facts.get("functions") or []):
                continue
        elif kind == "function" and section_kind == "per-package":
            # 패키지 색인은 함수도 선언 파일의 패키지로 묶어 싣는다(generate._per_package 와 같은 규칙).
            if not matches_symbol(name, facts.get("functions") or []):
                continue
            entity = snapshot.functions.get(name)
            loc = entity and (entity.loc or entity.def_loc)
            pkg_pats = facts.get("packages") or []
            if not loc or (pkg_pats and not package_selected(package_of(loc.file, package_depth), pkg_pats)):
                continue
        else:
            continue
        selected.add(section["id"])
    return selected


def _shape(snapshot: KnowledgeModel | None, kind: str, name: str):
    """위치와 설명을 뺀 엔티티 구조. #include 변경이 선언을 바꿨는지 가리는 데 쓴다."""
    if snapshot is None:
        return None
    if kind == "class":
        c = snapshot.classes.get(name)
        return None if c is None else (c.kind, tuple(sorted(c.bases)), tuple(sorted(m.name for m in c.methods)))
    return ("function",) if name in snapshot.functions else None


def audit(model: KnowledgeModel, files: list[str],
          base_model: KnowledgeModel | None = None, *, sections: list[dict], excluded: list[str],
          manual_evidence: dict[str, list[str]], impacted_sections: set[str],
          non_semantic: dict[str, str] | None = None, package_depth: int = 1) -> dict:
    """non_semantic: 주석·공백·#include 만 바뀐 파일과 그 이유 (change_kind.classify 결과).

    그 파일들에만 걸리고 이전·현재 facts 의 구조(종류·기반 클래스·메서드 이름)가 같은 항목은
    검토 항목(findings)이 아니라 자동 분류(classified)로 남긴다.
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
                item["sections"].update(_select_sections(kind, name, snapshot, sections, package_depth))

    items = []
    findings = []
    classified = []
    for key in sorted(entities):
        item = entities[key]
        item["files"] = sorted(item["files"])
        item["sections"] = sorted(item["sections"])
        reason = ("entity-outside-document-scope" if not item["sections"] else
                  "document-not-scheduled" if not impacted_sections.intersection(item["sections"]) else None)
        # 주석·공백·#include 만 바뀐 파일에 있어도, #include 가 선언을 바꿨을 수 있으므로
        # 이전·현재 facts 의 구조가 같다고 확인될 때만 분류한다. 이전 facts 가 없으면 분류하지 않는다.
        unchanged = (_shape(base_model, item["kind"], item["name"]) is not None
                     and _shape(base_model, item["kind"], item["name"]) == _shape(model, item["kind"], item["name"]))
        if reason and unchanged and all(f in non_semantic for f in item["files"]):
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
