"""증분 생성 뒤, 영향 밖 원고의 근거를 새 facts 로 재검증해 커밋 기준을 이월한다.

사이트 빌드는 facts 와 모든 원고의 source_commit 이 같아야 게시한다. 전체 재생성으로
기준을 맞추면 소형 모델이 감당하지 못하므로, 영향이 없던 원고는 LLM 을 부르지 않고
기존 본문의 `파일:줄` 인용이 새 facts 에도 전부 있는지 확인한 뒤 source_commit 만
승격한다. 인용이 하나라도 어긋나면 승격하지 않고 재생성 대상으로 보고한다. 조용히
통과시키지 않는다는 DESIGN.md 6번 계약을 따른다.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .facts.model import KnowledgeModel
from .validate import extract_citations
from .evidence import fingerprint, requires_fingerprint

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _meta(frontmatter: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if line[:1].isspace() or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def carry_forward(cfg: Config, model: KnowledgeModel,
                  written: list[Path]) -> tuple[list[Path], list[tuple[Path, list[str]]]]:
    """이번에 생성하지 않은 파이프라인 소유 페이지를 재검증한다.

    반환: (승격한 페이지, [(승격하지 못한 페이지, 새 facts 에 없는 인용)]).
    수동 페이지(kind: manual)와 파이프라인 frontmatter 가 없는 파일은 건드리지 않는다."""
    new_commit = str(model.meta.get("source_commit", ""))
    promoted: list[Path] = []
    stale: list[tuple[Path, list[str]]] = []
    if not new_commit:
        return promoted, stale

    done = {p.resolve() for p in written}
    allowed = model.citations()
    sections = {s["id"]: s for s in cfg.sections()}
    from .document_health import retired_paths
    retired = retired_paths(cfg)
    for path in sorted(cfg.sdd_dir.rglob("*.md")):
        if path.relative_to(cfg.sdd_dir).as_posix() in retired:
            continue
        if path.resolve() in done:
            continue
        text = path.read_text(encoding="utf-8")
        m = _FM.match(text)
        if not m:
            continue
        meta = _meta(m.group(1))
        # New pages record their generation method; legacy pages have an agent.
        if (meta.get("kind") == "manual" or meta.get("generation_method") == "manual"
                or "source_commit" not in meta or not ("agent" in meta or "generation_method" in meta)):
            continue
        old_commit = meta.get("source_commit", "")
        if old_commit == new_commit:
            continue

        body = text[m.end():]
        invalid = sorted({c for c in extract_citations(body) if c not in allowed})
        sec = sections.get(meta.get("section", ""), {})
        if sec.get("design_requirements"):
            from .design_contracts import audit
            invalid.extend(audit(model, sec)["findings"])
        if meta.get("scenario_fingerprint"):
            from .scenario_document import fingerprint as scenario_fingerprint
            sid = meta.get("scenario_id", "")
            settings = next((s for s in cfg.scenarios() if s["id"] == sid), {})
            sc = model.scenarios.get(sid)
            if sc is None or meta["scenario_fingerprint"] != scenario_fingerprint(sc, settings):
                invalid.append("시나리오 호출 근거 또는 표시 설정이 변경됐습니다.")
        if (requires_fingerprint(sec) or meta.get("evidence_fingerprint")) and meta.get("evidence_fingerprint") != fingerprint(model, sec):
            invalid.append("설계 질문·구조·소스 근거가 변경됐거나 이전 지문이 없습니다.")
        if invalid:
            stale.append((path, invalid))
            continue

        fm = re.sub(r"^source_commit:.*$", f"source_commit: {new_commit}", m.group(1), count=1, flags=re.M)
        fm = re.sub(r"^revalidated_from:.*\n?", "", fm, flags=re.M).rstrip()
        if old_commit:
            fm += f"\nrevalidated_from: {old_commit}"
        path.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8", newline="\n")
        promoted.append(path)
    return promoted, stale
