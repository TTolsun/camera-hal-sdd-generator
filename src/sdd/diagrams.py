"""Deterministic diagram policy shared by Markdown generation and site rendering."""

from __future__ import annotations

import html
import re

from .config import Config
from .matching import matches_symbol
from .facts.model import KnowledgeModel

POLICY_VERSION = 2


def scenario_call_map(messages: list, limit: int = 16) -> str:
    """A call relationship map avoids ordering unrelated dynamic candidates."""
    names = sorted({n for m in messages for n in (m.src, m.dst)})
    if limit < 1 or len(names) > limit:
        raise RuntimeError(f"Scenario diagram has {len(names)} nodes (limit {limit}); "
                           "narrow scenarios.focus or increase diagrams.max_nodes")
    ids = {name: f"p{i}" for i, name in enumerate(names)}
    rows = ["flowchart LR"]
    for name, ident in ids.items():
        rows.append(f'  {ident}["{html.escape(name, quote=True)}"]')
    edges = dict.fromkeys((m.src, m.dst, m.name, m.note) for m in messages)
    for source, target, name, note in edges:
        label = html.escape(f"{name}()" + (f" · {note}" if note else ""), quote=True)
        arrow = "-.->" if note else "-->"
        rows.append(f'  {ids[source]} {arrow}|"{label}"| {ids[target]}')
    return "\n".join(rows)

def class_diagram(model: KnowledgeModel, patterns: list[str], limit: int = 16, direction: str = "LR", strip_namespace: str = "") -> str:
    """Only declared classes and extracted edges; no inferred call ordering."""
    selected = {n for n in model.classes if matches_symbol(n, patterns)}
    if not selected:
        return ""
    if direction not in ("LR", "TB", "RL", "BT") or limit < 1:
        raise RuntimeError("Invalid diagram direction or max_nodes")
    names = set(selected)
    # Direct bases give the diagram context. Never expand the entire dependency graph.
    bases = {b for n in selected for b in model.classes[n].bases}
    if len(names | bases) > limit:
        raise RuntimeError(f"Diagram has {len(names | bases)} nodes (limit {limit}); narrow facts.classes or increase diagrams.max_nodes")
    names |= bases
    ids = {n: f"c{i}" for i, n in enumerate(sorted(names))}
    rows = [f"flowchart {direction}"]
    for name, ident in ids.items():
        label = html.escape(name.removeprefix(strip_namespace), quote=True)
        rows.append(f'  {ident}["{label}"]' + (":::context" if name not in selected else ""))
    edges = {(n, b, "inheritance") for n in selected for b in model.classes[n].bases}
    edges |= {(r.source, r.target, r.type) for r in model.relations
              if r.source in selected and r.target in names}
    labels = {"inheritance": "상속", "association": "필드 참조", "dependency": "의존",
              "aggregation": "집합", "composition": "합성"}
    for source, target, kind in sorted(edges):
        if kind in labels:
            arrow = "-.->" if kind == "inheritance" else "-->"
            rows.append(f"  {ids[source]} {arrow}|{labels[kind]}| {ids[target]}")
    rows.append("  classDef context fill:#fafafa,stroke:#aaa,stroke-dasharray:4 3,color:#555")
    return "\n".join(rows)


def section_diagram(cfg: Config, model: KnowledgeModel, section: dict) -> str:
    policy = cfg.diagram_policy(section)
    if not policy.get("enabled", False):
        return ""
    return class_diagram(model, section.get("facts", {}).get("classes", []),
                         limit=int(policy.get("max_nodes", 16)),
                         direction=str(policy.get("direction", "LR")),
                         strip_namespace=str(policy.get("strip_namespace", "")))


def _participant_id(name: str) -> str:
    """Mermaid 참여자 식별자. 영숫자와 밑줄만 남긴다.

    참여자 이름은 클래스 이름이거나, 클래스 밖 함수일 때는 파일 stem 이다. stem 에는 `-` 처럼
    Mermaid 가 식별자로 받지 않는 글자가 들어올 수 있어서(`gstlibcamera-utils`) 그림이 깨진다.
    """
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name).strip("_")
    return cleaned or "unknown"


def sequence_diagram(entry_owner: str, messages: list) -> str:
    """시나리오 메시지 목록으로 Mermaid 시퀀스를 만든다.

    facts 의 `Scenario.mermaid` 는 추출 시점의 전체 메시지로 만든 것이다. 생성 단계에서 표시를
    줄인 목록으로 다시 그려야 문서의 호출 순서 목록과 그림이 같은 내용을 가리킨다.
    """
    parts = ["sequenceDiagram"]
    seen: dict[str, str] = {}
    for name in [entry_owner] + [m.dst for m in messages]:
        if not name or name in seen:
            continue
        ident = _participant_id(name)
        seen[name] = ident
        parts.append(f"    participant {ident}" + (f" as {name}" if ident != name else ""))
    for m in messages:
        arrow = "-->>" if m.note else "->>"
        label = f"{m.name}()" + (f" [{m.note}]" if m.note else "")
        src = seen.get(m.src) or _participant_id(m.src)
        parts.append(f"    {src}{arrow}{seen[m.dst]}: {label}")
    return "\n".join(parts)



def diagram_block(source: str) -> str:
    if not source:
        return ""
    return ("\n<!-- sdd:class-diagram -->\n## 클래스 관계\n\n"
            "화살표의 글자는 추출한 관계를 나타내며, 점선은 상속입니다. "
            "화살표는 참조 대상 또는 기반 클래스를 향합니다. 호출 순서를 뜻하지 않습니다.\n\n"
            f"```mermaid\n{source}\n```\n<!-- /sdd:class-diagram -->\n\n")
