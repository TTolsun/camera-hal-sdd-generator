"""Git adapter for immutable revisions and source-relative changed paths."""

import subprocess
from pathlib import Path


def resolve_commit(source_root: Path, ref: str) -> str:
    return subprocess.check_output(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                                   cwd=source_root, encoding="utf-8").strip()


def commits_between(source_root: Path, base: str, to: str) -> list[str]:
    """base 다음부터 to 까지의 커밋을 오래된 것부터 차례대로. first-parent 만 따라간다."""
    out = subprocess.check_output(["git", "rev-list", "--reverse", "--first-parent", f"{base}..{to}"],
                                  cwd=source_root, encoding="utf-8")
    return [line for line in out.splitlines() if line]


def is_ancestor(source_root: Path, base: str, to: str) -> bool:
    """base 가 to 의 조상인지. base 가 이력에 없으면(rebase·force-push 뒤) False."""
    res = subprocess.run(["git", "merge-base", "--is-ancestor", base, to],
                         cwd=source_root, capture_output=True)
    return res.returncode == 0


def is_clean(source_root: Path) -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=source_root, encoding="utf-8")
    return not out.strip()


def checkout(source_root: Path, sha: str) -> None:
    subprocess.run(["git", "checkout", "--detach", "--quiet", sha], cwd=source_root, check=True)


def current_ref(source_root: Path) -> str:
    """현재 브랜치 이름. detached 상태면 커밋 SHA."""
    res = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"],
                         cwd=source_root, capture_output=True, encoding="utf-8")
    return res.stdout.strip() or resolve_commit(source_root, "HEAD")


def checkout_ref(source_root: Path, ref: str) -> None:
    """브랜치 이름이면 그 브랜치로 되돌린다 (detach 하지 않는다)."""
    subprocess.run(["git", "checkout", "--quiet", ref], cwd=source_root, check=True)


def fetch(source_root: Path) -> None:
    subprocess.run(["git", "fetch", "--quiet"], cwd=source_root, check=True)


def changed_files(source_root: Path, base: str, head: str = "HEAD") -> list[str]:
    # --relative: 소스 루트가 저장소의 하위 디렉터리여도 facts 의 file 과 같은 기준(소스 루트 상대)이 된다.
    res = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", "--relative", f"{base}..{head}", "--"], cwd=source_root,
                         check=True, capture_output=True, encoding="utf-8")
    return sorted(set(path for path in res.stdout.split("\0") if path))


def file_at(source_root: Path, rev: str, path: str) -> str | None:
    """소스 루트 상대 경로의 파일 내용을 그 커밋 기준으로 읽는다. 그 커밋에 없으면 None."""
    # ./ 를 붙여야 소스 루트가 저장소의 하위 디렉터리여도 소스 루트 기준으로 찾는다.
    try:
        res = subprocess.run(["git", "show", f"{rev}:./{path}"], cwd=source_root,
                             capture_output=True, encoding="utf-8", errors="replace")
    except OSError:                       # 소스 루트가 없거나 git 이 없으면 분류하지 않는다
        return None
    return res.stdout if res.returncode == 0 else None


def diff_text(source_root: Path, base: str, head: str, paths: list[str], limit: int = 6000) -> str:
    """사람이나 모델에게 보여 줄 unified diff. limit 를 넘으면 자르고 잘랐다고 적는다."""
    res = subprocess.run(["git", "diff", "--no-color", "--no-ext-diff", "--no-renames", "--relative",
                          f"{base}..{head}", "--", *paths],
                         cwd=source_root, check=True, capture_output=True, encoding="utf-8", errors="replace")
    text = res.stdout
    return text if len(text) <= limit else text[:limit] + f"\n... (diff {len(text) - limit}자 생략)\n"
