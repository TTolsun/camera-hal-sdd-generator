"""Read review evidence declared by human-authored Markdown pages."""

import re
from pathlib import Path

import yaml


GENERATION_METHODS = {
    "source-bound-contract": ("소스 발췌에 연결한 설계 설명",
                              "설정에 작성된 설명을 발췌 해시와 대조합니다. 해시 일치는 설명의 의미를 승인하지 않습니다."),
    "extracted-structure": ("추출 사실로 만든 구조 설명", "클래스와 관계를 facts에서 구성합니다. 실행 동작을 검증하지 않습니다."),
    "extracted-scenario": ("추출 호출로 만든 시나리오", "주요 호출과 경계를 facts에서 구성하고 전체 추적 기록을 보존합니다. 실행 순서를 추정하지 않습니다."),
    "facts-and-llm": ("추출 사실과 LLM 설명", "표·그림은 facts로 만들고 설명은 LLM이 작성합니다. 인용·문장 및 설정된 구조 검사를 적용합니다."),
    "mixed": ("소스 근거 설명과 LLM 설명의 혼합", "절마다 소스 발췌에 연결한 설명 또는 LLM 설명을 사용합니다."),
    "deterministic": ("추출 사실과 설정으로 생성", "표와 목록을 facts 또는 문서 설정에서 구성합니다. LLM을 호출하지 않습니다."),
    "manual": ("사람이 작성하는 문서", "설계 결정과 실행 관찰을 사람이 작성하고 검토합니다."),
    "dry-run": ("생성 절차 점검용 초안", "LLM을 호출하지 않은 초안입니다. 설명 품질 검사를 통과한 문서가 아닙니다."),
}


def generation_method(section: dict, agent_kind: str) -> str:
    kind = section.get("kind", "prose")
    if kind == "manual":
        return "manual"
    if kind in ("index", "table"):
        return "deterministic"
    if kind == "per-scenario" and section.get("narration", "facts") == "facts":
        return "extracted-scenario"
    if kind == "per-package" and section.get("narration") == "facts":
        return "extracted-structure"
    topics = (section.get("design_topics") or []) if kind == "prose" else []
    if topics and all("statements" in topic for topic in topics):
        return "source-bound-contract"
    if kind == "prose" and not topics and section.get("narration") == "facts":
        return "extracted-structure"
    if agent_kind == "dry-run":
        return "dry-run"
    if any("statements" in topic for topic in topics):
        return "mixed"
    return "facts-and-llm"


def generation_info(method: str) -> tuple[str, str]:
    return GENERATION_METHODS.get(method, ("생성 방식 미기록", "기존 원고에 생성 방식이 기록되지 않았습니다. 다시 생성하면 표시됩니다."))


def manual_evidence_files(path: Path) -> list[str]:
    """manual 문서 frontmatter 의 evidence_files 목록. 없으면 빈 목록."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return []
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    return [str(f).replace("\\", "/") for f in (data.get("evidence_files") or [])]
