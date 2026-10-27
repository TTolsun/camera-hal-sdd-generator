"""변경 영향 매핑: git diff -> 변경 파일/심볼 -> 재생성할 SDD 섹션과 시나리오.

경로와 근거, 심볼 규칙으로 잡는다.
1. 경로·근거 규칙: watch glob 또는 design_topics의 소스 파일이 바뀌면 그 섹션.
2. 심볼 규칙: 변경 파일에 정의된 클래스가 속한 패키지, 변경 파일을 지나는 시나리오.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import source_git
from .change_kind import classify
from .config import Config
from .coverage import audit, outside_build
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

    # 1. 경로 규칙. 분석한 빌드가 읽지 않은 C/C++ 파일은 문서 내용을 바꾸지 않으므로 다시 만들 계기로 보지 않는다.
    unbuilt = outside_build(files, model, base_model)
    for sec in sections:
        hits = [f for f in files if f not in unbuilt and match_any(f, sec.get("watch", []) or [])]
        if hits:
            report.sections.setdefault(sec["id"], []).append(f"watch 일치: {', '.join(hits[:5])}")
        # Authored and model-generated contracts depend on excerpts without selected
        # symbols or watch globs. Explicit evidence can also be outside the
        # compile DB (for example build configuration or interface headers).
        evidence_files = {PurePosixPath(source["file"]).as_posix() for topic in sec.get("design_topics", [])
                          for source in topic.get("sources", []) if isinstance(source.get("file"), str)}
        evidence_hits = sorted(fileset.intersection(evidence_files))
        if evidence_hits:
            report.sections.setdefault(sec["id"], []).append(f"설계 근거 파일 변경: {', '.join(evidence_hits[:5])}")

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


def config_changes(cfg: Config, model: KnowledgeModel) -> dict[str, list[str]]:
    """소스 diff 없이 설계 질문·근거 지정·facts 선택이 바뀌어 다시 만들어야 하는 섹션과 이유.

    원고는 생성할 때의 입력 지문(`evidence_fingerprint`)을 기록한다. 현재 설정과 facts로 계산한 지문이
    다르면 그 원고는 지금의 질문·근거에 답하지 않으므로 영향 섹션이다. 표시용 설정(메뉴, 이동 안내,
    다음 문서)은 지문에 들어가지 않아 재생성을 요구하지 않는다. 모델에 쓰는 evidence 는 먼저 수집해 두어야 한다."""
    from .config import section_output
    from .document_metadata import split_frontmatter
    from .evidence import fingerprint
    changed: dict[str, list[str]] = {}
    for sec in cfg.sections():
        if sec.get("kind") == "manual" or not (sec.get("design_topics") or sec.get("reader_profile")):
            continue
        path = cfg.sdd_dir / section_output(sec)
        if not path.is_file():
            changed[sec["id"]] = ["원고가 아직 없음"]
            continue
        text = path.read_text(encoding="utf-8")
        recorded = str(split_frontmatter(text)[0].get("evidence_fingerprint", ""))
        if recorded != fingerprint(model, sec):
            changed[sec["id"]] = ["설계 질문·근거 지정이 원고를 만든 입력과 다름" if recorded else "원고에 입력 지문이 없음"]
            continue
        if sec.get("design_generation") == "llm":
            # 입력은 같아도 저장된 답변이 현재 검사(중복 문장, 문장 형태)나 표시 형식을 통과하지 못하면
            # 같은 답변으로 다시 만들거나 해당 주제만 다시 쓰게 한다.
            from . import generated_design
            try:
                repeated = generated_design.verify(model, sec, text, cfg=cfg).get("repeated_sentences")
                if repeated:
                    changed[sec["id"]] = ["같은 근거로 같은 내용을 되풀이한 문장이 있음: " + repeated[0][:100]]
            except (ValueError, TypeError, KeyError) as exc:
                changed[sec["id"]] = ["저장된 설계 답변이 현재 검사·표시 형식과 다름: " + str(exc)[:120]]
    return changed


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
