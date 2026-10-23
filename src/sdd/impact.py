"""변경 영향 매핑: git diff -> 변경 파일/심볼 -> 재생성할 SDD 섹션과 시나리오.

두 단계로 잡는다.
1. 경로 규칙: sections.yaml 의 watch glob 에 변경 파일이 걸리면 그 섹션.
2. 심볼 규칙: 변경 파일에 정의된 클래스가 속한 패키지, 변경 파일을 지나는 시나리오.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import source_git
from .change_kind import classify
from .config import Config
from .coverage import audit
from .document_metadata import manual_evidence_files
from .matching import match_any, matches_symbol
from .facts.model import KnowledgeModel


@dataclass
class ImpactReport:
    base: str
    head: str
    changed_files: list[str] = field(default_factory=list)
    changed_classes: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)     # section id -> 이유
    scenarios: dict[str, list[str]] = field(default_factory=dict)    # scenario id -> 이유
    packages: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, path: Path) -> "ImpactReport":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def non_semantic_files(cfg: Config, files: list[str], base: str, head: str) -> dict[str, str]:
    """주석·공백·#include 만 바뀐 파일과 그 이유. 범위 검사는 이 파일들을 검토 항목에서 뺀다."""
    out = {}
    for path in files:
        reason = classify(path, source_git.file_at(cfg.source_root, base, path),
                          source_git.file_at(cfg.source_root, head, path))
        if reason:
            out[path] = reason
    return out


def compute(cfg: Config, model: KnowledgeModel, files: list[str], base: str, head: str,
            base_model: KnowledgeModel | None = None,
            non_semantic: dict[str, str] | None = None) -> ImpactReport:
    """non_semantic 을 주지 않으면 소스 저장소에서 두 판을 읽어 직접 분류한다."""
    report = ImpactReport(base=base, head=head, changed_files=files)
    fileset = set(files)
    sections = cfg.sections()
    manual_evidence = {s["id"]: manual_evidence_files(cfg.sdd_dir / s.get("output", f"{s['id']}.md"))
                       for s in sections if s.get("kind") == "manual"}

    # 1. 경로 규칙
    for sec in sections:
        hits = [f for f in files if match_any(f, sec.get("watch", []) or [])]
        if hits:
            report.sections.setdefault(sec["id"], []).append(f"watch 일치: {', '.join(hits[:5])}")

    # 2. 심볼 규칙
    changed_classes = model.classes_in_files(fileset)
    report.changed_classes = sorted(c.name for c in changed_classes)
    report.packages = sorted({c.package for c in changed_classes if c.package})
    for sec in sections:
        facts = sec.get("facts", {})
        # impact_classes 가 있으면 그것을, 없으면 classes 를 쓴다 (개요처럼 인용용으로만 클래스를 넘기는 절 대응).
        patterns = facts.get("impact_classes", facts.get("classes")) or []
        if not patterns:
            continue
        hit = [c.name for c in changed_classes if matches_symbol(c.name, patterns)]
        if hit:
            report.sections.setdefault(sec["id"], []).append(f"클래스 변경: {', '.join(hit[:5])}")
    # 자유 함수도 같은 규칙으로 본다. impact_functions 가 있으면 그것을, 없으면 functions 를 쓴다.
    changed_functions = sorted(name for name, fn in model.functions.items()
                               if any(loc and loc.file in fileset for loc in (fn.loc, fn.def_loc)))
    for sec in sections:
        facts = sec.get("facts", {})
        patterns = facts.get("impact_functions", facts.get("functions")) or []
        hit = [name for name in changed_functions if matches_symbol(name, patterns)]
        if hit:
            report.sections.setdefault(sec["id"], []).append(f"함수 변경: {', '.join(hit[:5])}")

    for sc in model.scenarios_touching(fileset):
        report.scenarios.setdefault(sc.id, []).append("시나리오 경로에 포함된 파일이 변경됨")
    if report.scenarios:
        report.sections.setdefault("scenarios", []).append(f"영향 시나리오: {', '.join(sorted(report.scenarios))}")

    # 3. 사람이 쓰는 문서: frontmatter 의 evidence_files 가 바뀌면 재검토 대상으로 올린다 (재생성은 하지 않는다).
    for sec in sections:
        if sec.get("kind") != "manual":
            continue
        evidence = manual_evidence[sec["id"]]
        hit = sorted(fileset.intersection(evidence))
        if hit:
            report.sections.setdefault(sec["id"], []).append(f"수동 문서의 근거 파일 변경: {', '.join(hit[:5])} (사람이 재검토)")

    if non_semantic is None:
        non_semantic = non_semantic_files(cfg, [f for f in files if not match_any(f, cfg.exclude)], base, head)
    report.coverage = audit(model, files, base_model, sections=sections, excluded=cfg.exclude,
                            manual_evidence=manual_evidence, impacted_sections=set(report.sections),
                            non_semantic=non_semantic, package_depth=cfg.package_depth)
    return report


def summary_facts(report: ImpactReport, model: KnowledgeModel) -> str:
    """change_impact 프롬프트에 넣을 사실 블록."""
    lines = [f"- 비교 범위: {report.base}..{report.head}", f"- 변경 파일 {len(report.changed_files)} 개:"]
    lines += [f"  - {f}" for f in report.changed_files[:30]]
    if report.changed_classes:
        lines.append("- 변경된 파일에 정의된 클래스:")
        for name in report.changed_classes[:30]:
            c = model.classes[name]
            lines.append(f"  - {name} ({c.loc.cite() if c.loc else '위치 없음'})")
    if report.scenarios:
        lines.append("- 영향 받는 시나리오: " + ", ".join(sorted(report.scenarios)))
    lines.append("- 재생성된 SDD 섹션: " + ", ".join(sorted(report.sections)) if report.sections else "- 재생성된 섹션 없음")
    if report.coverage:
        lines.append(f"- 문서 범위 검사: {report.coverage['status']} (설명 정확성이나 승인 판정이 아님)")
        for item in report.coverage["findings"][:30]:
            lines.append(f"  - 검토 필요: {item['name']} ({item['reason']})")
        lines.append(f"- 전체 범위 검토 {len(report.coverage['findings'])}개는 build/impact-review.md에서 확인")
    return "\n".join(lines)
