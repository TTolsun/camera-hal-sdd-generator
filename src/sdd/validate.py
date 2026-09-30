"""LLM 출력 검증: 인용된 file:line 이 facts 에 실제로 존재하는지 확인한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Capture the whole citation-shaped token, including malformed namespace/URL prefixes.
# A narrow path alphabet silently ignored invalid citations mixed with valid ones.
_CITE = re.compile(r"`([^`\s]+\.(?:cpp|cc|c|h|hpp|mk|tmpl)):(\d+)`")
_CLAIM_WORDS = ("클래스", "함수", "호출", "메서드", "플래그", "상속", "생성", "반환")


@dataclass
class Verdict:
    ok: bool
    invalid: list[str] = field(default_factory=list)
    total: int = 0
    uncited_paragraphs: int = 0
    notes: list[str] = field(default_factory=list)


def extract_citations(text: str) -> list[str]:
    return [f"{f.replace(chr(92), '/')}:{n}" for f, n in _CITE.findall(text)]


def normalize_citations(text: str, allowed: set[str]) -> str:
    """소형 모델이 디렉터리를 빼고 `CameraModule.cpp:17` 처럼 인용하면, allowed 안에서 basename 과 줄이
    유일하게 일치하는 `module/CameraModule.cpp:17` 로 바꿔 준다. 애매하면 손대지 않는다."""
    by_base: dict[str, list[str]] = {}
    for c in allowed:
        by_base.setdefault(c.rsplit("/", 1)[-1], []).append(c)

    def fix(m: re.Match[str]) -> str:
        cite = f"{m.group(1).replace(chr(92), '/')}:{m.group(2)}"
        if cite in allowed:
            return m.group(0)
        cands = by_base.get(cite.rsplit("/", 1)[-1], [])
        return f"`{cands[0]}`" if len(cands) == 1 else m.group(0)

    return _CITE.sub(fix, text)


def strip_headings(text: str) -> str:
    """LLM 이 지시를 어기고 넣은 제목 줄을 뺀다. 제목은 파이프라인이 붙인다."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#")).strip()


def strip_echo(text: str, prompt: str) -> str:
    """소형 모델이 프롬프트(사실 목록, 표, 지시문)를 그대로 되풀이한 줄을 뺀다.

    프롬프트에 있던 줄과 공백을 무시하고 같은 줄만 지운다. 모델이 새로 쓴 문장은 남는다."""
    seen = {" ".join(l.split()) for l in prompt.splitlines() if len(l.strip()) >= 8}
    kept = [l for l in text.splitlines()
            if " ".join(l.split()) not in seen and l.strip() not in ("---", "***", "___")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)


def check(text: str, allowed: set[str], require: bool = True) -> Verdict:
    cites = extract_citations(text)
    invalid = sorted({c for c in cites if c not in allowed})
    v = Verdict(ok=True, invalid=invalid, total=len(cites))

    # 클래스/함수를 언급하는 문단인데 인용이 하나도 없으면 센다. 실패 사유는 아니고 리뷰 힌트.
    for para in [p for p in text.split("\n\n") if p.strip()]:
        if any(w in para for w in _CLAIM_WORDS) and not _CITE.search(para):
            v.uncited_paragraphs += 1

    if invalid:
        v.ok = False
        v.notes.append(f"facts 에 없는 인용 {len(invalid)} 개: {', '.join(invalid[:5])}")
    if require and not cites:
        v.ok = False
        v.notes.append("인용이 하나도 없습니다.")
    if _TABLE_ROW.search(text):
        v.ok = False
        v.notes.append("표를 출력했습니다. 표는 파이프라인이 만듭니다. 문단만 씁니다.")
    if len(text.strip()) < 80:
        v.ok = False
        v.notes.append("본문이 비어 있거나 너무 짧습니다.")
    if v.uncited_paragraphs:
        v.notes.append(f"클래스나 함수를 언급하면서 인용이 없는 문단 {v.uncited_paragraphs} 개")
    return v
