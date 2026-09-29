"""Retry-safe synchronization of manifest-owned artifacts to a dedicated Git clone."""
import json
import shutil
import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request
import tempfile
from pathlib import Path

from .site_build import MANIFEST, digest, owned_path


def verify_remote(site, url, *, timeout=600, interval=10):
    """Wait for the expected build and verify every published artifact's digest."""
    from .site_build import verify_site
    verify_site(site)
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
        raise ValueError("게시 사이트의 http(s) 기본 URL이 필요합니다. query/fragment는 제외하세요.")
    if timeout <= 0 or interval <= 0:
        raise ValueError("timeout과 interval은 양수여야 합니다.")
    expected = json.loads((site / MANIFEST).read_text(encoding="utf-8"))
    deadline = time.monotonic() + timeout
    error = "게시 대기"
    while time.monotonic() < deadline:
        try:
            def read(rel):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("게시 확인 시간 초과")
                address = url.rstrip("/") + "/" + urllib.parse.quote(rel, safe="/")
                request = urllib.request.Request(address, headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(request, timeout=min(30, remaining)) as response:
                    return response.read()
            actual = json.loads(read(MANIFEST))
            if actual != expected:
                raise ValueError("게시 manifest가 기대한 산출물과 다릅니다.")
            for rel, sha in expected["outputs"].items():
                if hashlib.sha256(read(rel)).hexdigest() != sha:
                    raise ValueError(f"게시된 파일 해시 불일치: {rel}")
            return expected["build_id"]
        except (OSError, ValueError, urllib.error.URLError) as exc:
            error = str(exc)
            time.sleep(max(0, min(interval, deadline - time.monotonic())))
    raise RuntimeError(f"게시 확인 실패: {error}")


def copy_site(stage, out, scratch=None):
    current = json.loads((stage / MANIFEST).read_text(encoding="utf-8"))
    prior_path = out / MANIFEST
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {"outputs": {}}
    old, new = prior["outputs"], current["outputs"]
    # An interrupted copy may contain either the old or new version of each file.
    for rel in old.keys() | new.keys():
        target = owned_path(out, rel)
        if target.exists():
            if not target.is_file() or digest(target) not in {old.get(rel), new.get(rel)}:
                raise RuntimeError(f"수동 수정되었거나 관리하지 않는 게시 파일입니다: {rel}")
            if rel not in old and digest(target) != new.get(rel):
                raise RuntimeError(f"Unmanaged publication file: {rel}")
        for parent in target.parents:
            if parent.exists() and not parent.is_dir():
                raise RuntimeError(f"Publication directory conflict: {parent}")
            if parent == out:
                break
    out.mkdir(parents=True, exist_ok=True)
    # The caller supplies Git's private metadata directory: same filesystem,
    # outside tracked content. A killed process cannot leave a half-written page.
    if scratch is not None:
        scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdd-copy-", dir=scratch) as temporary:
        temp = Path(temporary) / "file"
        for rel in new:
            target = owned_path(out, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(owned_path(stage, rel), temp)
            temp.replace(target)
        for rel in old.keys() - new.keys():
            owned_path(out, rel).unlink(missing_ok=True)
        shutil.copyfile(stage / MANIFEST, temp)
        temp.replace(prior_path)
