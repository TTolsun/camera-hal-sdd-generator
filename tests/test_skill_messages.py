"""사내 에이전트 스킬과 사내 운영 문서가 인용하는 CLI 문구가 실제 코드에 남아 있는지 확인한다.

에이전트는 출력 문구로 다음 행동을 고른다. 코드에서 문구가 바뀌었는데 스킬이 옛 문구를 찾으면
에이전트가 오류를 알아보지 못하므로, 문구를 바꾸면 이 테스트가 스킬과 가이드 갱신을 요구한다.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "sdd").rglob("*.py"))
SKILL = (ROOT / "skills" / "camera-hal-sdd" / "SKILL.md").read_text(encoding="utf-8")
GUIDE = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "docs" / "inhouse").glob("*.md")))

QUOTED = [
    "파싱 오류",
    "진입점 못 찾음",
    "Clang 파싱 오류",
    "컴파일러가 clang 이 아니라 실행하지 않습니다",
    "clang 내장 헤더 위치를 확인하지 못했습니다",
    "진입 함수를 정하지 못했습니다",
    "같은 이름의 정의가",
    "응답 파일(@...)",
    "소스 저장소에 커밋되지 않은 변경이 있습니다",
    "broken_links",
    "함수 포인터, 정적 추적 불가",
    "근거 본문이 변경됐습니다",
    "design-review.json",
]


@pytest.mark.parametrize("text", QUOTED)
def test_스킬이_인용한_문구가_코드에_있다(text):
    assert text in SKILL, f"스킬에서 빠진 문구: {text}"
    assert text in SOURCE, f"코드에서 바뀐 문구: {text}. skills/ 와 docs/inhouse/troubleshooting.md 를 함께 고치세요."


def test_가이드가_스킬과_같은_설정_키를_쓴다():
    for key in ("source.ndk_build.clang", "update.compdb_cmd", ".git/info/exclude", "build/compdb/compile_commands.json"):
        assert key in GUIDE
    for key in ("source.ndk_build.clang", ".git/info/exclude"):
        assert key in SKILL


def test_스킬_frontmatter_가_Agent_Skills_형식이다():
    head, _, _ = SKILL.partition("\n---\n")
    assert head.startswith("---\n")
    fields = dict(line.split(": ", 1) for line in head.splitlines()[1:] if ": " in line and not line.startswith(" "))
    assert fields["name"] == "camera-hal-sdd"
    assert 0 < len(fields["description"]) <= 1024
