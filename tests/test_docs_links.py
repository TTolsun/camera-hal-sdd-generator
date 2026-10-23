"""저장소 문서의 상대 링크와 앵커가 실제로 있는지 확인한다.

문서를 옮기거나 절 제목을 바꾸면 다른 문서의 링크가 조용히 깨진다. 문서 구조를 지키는 장치다.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", "build", "node_modules", ".git", ".claude"}
LINK = re.compile(r"\]\(([^)\s]+)\)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.M)   # [이름]: 경로
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)


def _docs():
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT)
        if SKIP.intersection(rel.parts) or rel.parts[:2] == ("examples", "mini-hal") and "expected-output" in rel.parts:
            continue
        if rel.parts[0] == "sdd" or path.name == "site-intro.md":   # 생성 원고, 게시 사이트 기준 링크
            continue
        yield path


def _slug(heading: str) -> str:
    # GitHub 방식: 소문자, 글자·숫자·공백·하이픈만 남기고 공백은 하이픈으로.
    text = re.sub(r"`", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    # GitHub 와 같이 이미 쓴 id 와 겹치지 않을 때까지 -1, -2 를 붙인다.
    counts: dict[str, int] = {}
    used: set[str] = set()
    for heading in re.findall(r"^#{1,6} (.+)$", text, re.M):
        base = _slug(heading)
        n = counts.get(base, 0)
        candidate = base if n == 0 else f"{base}-{n}"
        while candidate in used:
            n += 1
            candidate = f"{base}-{n}"
        counts[base] = n + 1
        used.add(candidate)
    return used


def _links():
    for path in _docs():
        text = FENCE.sub("", path.read_text(encoding="utf-8"))
        for target in LINK.findall(text) + REFERENCE.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("{"):
                continue
            yield path, target


def test_중복_제목은_이미_쓴_id_와_겹치지_않게_번호를_붙인다(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("## A\n\n## A\n\n## A 1\n\n## A\n", encoding="utf-8")
    assert _anchors(page) == {"a", "a-1", "a-1-1", "a-2"}


@pytest.mark.parametrize("path,target", list(_links()), ids=lambda v: str(v)[-60:])
def test_문서_링크가_가리키는_파일과_절이_있다(path, target):
    file, _, anchor = target.partition("#")
    dest = (path.parent / file).resolve() if file else path
    assert dest.exists(), f"{path.relative_to(ROOT)}: 없는 파일 {target}"
    if anchor and dest.suffix == ".md":
        assert anchor in _anchors(dest), f"{path.relative_to(ROOT)}: {dest.name} 에 #{anchor} 절이 없습니다"
