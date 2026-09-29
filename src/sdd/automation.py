"""Resumable scheduled publication. Scheduling and deployment are explicit adapters."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import approvals, source_git, update
from .export_site import export_site
from .facts.model import KnowledgeModel
from .site_build import MANIFEST, verify_site


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextmanager
def locked(path):
    """OS lock is released even after a crash. The lock file is never unlinked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("같은 설정의 자동화 작업이 이미 실행 중입니다.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def cron(cfg, config_path):
    """Render a user crontab entry for CRON_TZ-capable cron (e.g. Cronie)."""
    schedule = cfg.raw.get("automation", {}).get("schedule", {})
    at, zone = str(schedule.get("time", "")), str(schedule.get("timezone", ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
        raise ValueError("automation.schedule.time에 HH:MM을 지정하세요.")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("유효한 IANA timezone이 필요합니다 (예: Asia/Seoul).") from exc
    command = schedule.get("command")
    _command(command, "schedule.command")
    args = [a.replace("{config}", str(config_path)) for a in command]
    if not any("{config}" in a for a in command):
        raise ValueError("schedule.command에는 {config}가 필요합니다.")
    if any("\n" in a or "\r" in a for a in args):
        raise ValueError("cron 명령에 줄바꿈을 넣을 수 없습니다.")
    hour, minute = map(int, at.split(":"))
    quoted = shlex.join(args).replace("%", r"\%")
    return f"CRON_TZ={zone}\n{minute} {hour} * * * {quoted}\n"


def _command(value, label):
    if not isinstance(value, list) or not value or any(not isinstance(a, str) or not a for a in value):
        raise ValueError(f"{label}은 비어 있지 않은 명령 인자 목록이어야 합니다.")


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, encoding="utf-8").strip()


def _settings(cfg):
    opts = cfg.raw.get("automation", {})
    if not isinstance(opts, dict):
        raise ValueError("automation 설정은 객체여야 합니다.")
    pub = opts.get("publish", {})
    if not isinstance(pub, dict) or not isinstance(opts.get("hermes", {}), dict):
        raise ValueError("publish와 hermes 설정은 객체여야 합니다.")
    if int(pub.get("timeout_sec", 900)) <= 0:
        raise ValueError("publish.timeout_sec은 양수여야 합니다.")
    for key in ("repo", "directory", "remote", "branch"):
        if not isinstance(pub.get(key), str) or not pub[key].strip():
            raise ValueError(f"automation.publish.{key}가 필요합니다.")
    if pub["remote"].startswith("-") or pub["branch"].startswith("-"):
        raise ValueError("Git remote/branch는 옵션으로 시작할 수 없습니다.")
    _command(pub.get("verify_command"), "publish.verify_command")
    if pub.get("deploy_command") is not None:
        _command(pub["deploy_command"], "publish.deploy_command")
    repo = (cfg.root / pub["repo"]).resolve()
    out = (repo / pub["directory"]).resolve()
    source = cfg.source_root.resolve()
    if repo == source or repo in source.parents or source in repo.parents:
        raise ValueError("분석 소스와 문서 저장소는 서로 분리된 작업본이어야 합니다.")
    if not out.is_relative_to(repo) or out == repo or ".git" in out.relative_to(repo).parts:
        raise ValueError("게시 디렉터리는 문서 저장소 내부의 전용 하위 디렉터리여야 합니다.")
    for protected in (cfg.source_root, cfg.root, cfg.sdd_dir, cfg.facts_dir):
        protected = protected.resolve()
        if out == protected or out in protected.parents or protected == repo:
            raise ValueError("게시 디렉터리와 소스·설정·원고·facts 경로를 분리하세요.")
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("publish.repo는 문서 저장소 루트여야 합니다.")
    git(repo, "check-ref-format", "refs/heads/" + pub["branch"])
    if source_git.current_ref(repo) != pub["branch"]:
        raise ValueError("문서 저장소를 설정한 게시 브랜치로 체크아웃하세요.")
    if not opts.get("to") or not isinstance(opts["to"], str) or opts["to"].startswith("-"):
        raise ValueError("automation.to에 추적할 ref를 명시하세요.")
    return opts, pub, repo, out


def _hook(command, repo, job, out, timeout):
    env = dict(os.environ, SDD_SOURCE_COMMIT=job["target"], SDD_SITE_DIR=str(out),
               SDD_DOCS_COMMIT=job["docs_commit"], SDD_BUILD_ID=job["build_id"])
    try:
        subprocess.run(command, cwd=repo, env=env, check=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("배포/확인 명령의 실행 시간이 초과됐습니다.") from exc


def run(cfg):
    with locked(cfg.build_dir / "automation.lock"):
        opts, pub, repo, out = _settings(cfg)
        path = cfg.build_dir / "automation-state.json"
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema": 1}
        if state.get("schema") != 1:
            raise ValueError("지원하지 않는 automation state schema입니다.")
        # A pending publication cannot silently switch destination or source.
        identity = hashlib.sha256(json.dumps({"options": {k: v for k, v in opts.items() if k != "schedule"}, "source": str(cfg.source_root),
                                             "repo": str(repo), "site": cfg.raw.get("site", {})}, sort_keys=True).encode()).hexdigest()
        job = state.get("pending")
        if job and job.get("phase") not in {"update", "build", "copy", "commit", "push", "deploy", "verify"}:
            raise ValueError("지원하지 않는 게시 단계입니다.")
        if job and job["identity"] != identity:
            raise RuntimeError("미완료 작업의 설정이 바뀌었습니다. 기존 설정으로 먼저 재개하세요.")
        if not job:
            if not source_git.is_clean(repo):
                raise RuntimeError("문서 저장소에 기존 변경이 있습니다. 전용 작업본을 정리하세요.")
            # Do not publish pre-existing local commits as a side effect.
            git(repo, "fetch", pub["remote"], pub["branch"])
            remote_head = source_git.resolve_commit(repo, "FETCH_HEAD")
            local_head = source_git.resolve_commit(repo, "HEAD")
            if not source_git.is_ancestor(repo, local_head, remote_head):
                raise RuntimeError("문서 저장소에 미게시 커밋 또는 분기된 이력이 있습니다.")
            git(repo, "merge", "--ff-only", remote_head)
            if opts.get("fetch", True):
                source_git.fetch(cfg.source_root)
            target = source_git.resolve_commit(cfg.source_root, opts["to"])
            job = {"identity": identity, "target": target, "phase": "update", "initial_docs_commit": remote_head}
            state["pending"] = job
            save(path, state)
        try:
            return _resume(cfg, opts, pub, repo, out, path, state, job)
        except Exception as exc:
            state["error"] = str(exc)
            save(path, state)
            raise


def _resume(cfg, opts, pub, repo, out, path, state, job):
    def phase(name):
        job["phase"] = name
        state.pop("error", None)
        save(path, state)

    if job["phase"] == "update":
        def generate(config, model, report):
            if opts.get("hermes", {}).get("enabled", False):
                from .hermes_review import revise
                revise(config, model, report, opts["hermes"])
            update._default_generate(config, model, report)
        result = update.run_update(cfg, to=job["target"], steps=update.Steps(generate=generate))
        if result.exit_code:
            state["error"] = result.stopped_reason
            save(path, state)
            return result.exit_code
        if update._needs_review_pages(cfg, approvals.load(cfg)):
            raise RuntimeError("needs-review 문서가 남아 있어 게시하지 않습니다.")
        if KnowledgeModel.load(cfg.facts_path).meta.get("source_commit") != job["target"]:
            raise RuntimeError("facts가 이번 게시 대상 커밋과 다릅니다.")
        phase("build")
    if job["phase"] == "build":
        if source_git.resolve_commit(repo, "HEAD") != job["initial_docs_commit"] or not source_git.is_clean(repo):
            raise RuntimeError("사이트 빌드 전에 문서 작업본이 변경됐습니다.")
        # Build outside Git first. On failure the existing published tree is preserved.
        staged = export_site(cfg, out=cfg.build_dir / "automation-site")
        verify_site(staged)
        manifest = json.loads((staged / MANIFEST).read_text(encoding="utf-8"))
        job["build_id"] = manifest["build_id"]
        phase("copy")
    if job["phase"] == "copy":
        from .publication import copy_site
        staged = cfg.build_dir / "automation-site"
        verify_site(staged)
        if json.loads((staged / MANIFEST).read_text(encoding="utf-8"))["build_id"] != job["build_id"]:
            raise RuntimeError("대기 중인 게시 산출물이 변경됐습니다.")
        if source_git.resolve_commit(repo, "HEAD") != job["initial_docs_commit"]:
            raise RuntimeError("문서 저장소 HEAD가 게시 도중 변경됐습니다.")
        if "owned" not in job:
            old_manifest = out / MANIFEST
            old = json.loads(old_manifest.read_text(encoding="utf-8"))["outputs"] if old_manifest.exists() else {}
            new = json.loads((staged / MANIFEST).read_text(encoding="utf-8"))["outputs"]
            job["owned"] = sorted(set(old) | set(new) | {MANIFEST})
            save(path, state)
        metadata = Path(git(repo, "rev-parse", "--absolute-git-dir"))
        copy_site(staged, out, scratch=metadata / "sdd-publication")
        phase("commit")
    if job["phase"] == "commit":
        verify_site(out)
        if (out / MANIFEST).read_bytes() != (cfg.build_dir / "automation-site" / MANIFEST).read_bytes():
            raise RuntimeError("게시 대기 중인 manifest가 변경됐습니다.")
        rel = out.relative_to(repo).as_posix()
        head = source_git.resolve_commit(repo, "HEAD")
        if head != job["initial_docs_commit"]:
            # Recover a crash after git commit but before checkpoint persistence.
            if (not job.get("tree") or git(repo, "show", "-s", "--format=%T", "HEAD") != job["tree"]
                    or git(repo, "show", "-s", "--format=%P", "HEAD") != job["initial_docs_commit"]):
                raise RuntimeError("게시 도중 예상하지 않은 문서 커밋이 추가됐습니다.")
        dirty = git(repo, "status", "--porcelain", "--untracked-files=all", "--", ".", f":(exclude,literal){rel}")
        if dirty:
            raise RuntimeError("게시 경로 밖에 변경된 파일이 있습니다.")
        git(repo, "add", "--", ":(literal)" + rel)
        # Only the intended site may be included in this commit.
        paths = [p for p in git(repo, "diff", "--cached", "--name-only", "-z").split("\0") if p]
        allowed = {rel + "/" + p for p in job["owned"]}
        if any(p not in allowed for p in paths):
            raise RuntimeError("게시 경로 밖에 staged 변경이 있습니다.")
        if paths:
            job["tree"] = git(repo, "write-tree")
            save(path, state)
            git(repo, "commit", "-m", f"docs: update SDD for {job['target']}")
        job["docs_commit"] = source_git.resolve_commit(repo, "HEAD")
        phase("push")
    if source_git.resolve_commit(repo, "HEAD") != job["docs_commit"] or not source_git.is_clean(repo):
        raise RuntimeError("게시 대기 중인 문서 커밋 또는 작업본이 변경됐습니다.")
    if job["phase"] == "push":
        if state.get("last_published") == {k: job[k] for k in ("target", "docs_commit", "build_id")}:
            state.pop("pending")
            save(path, state)
            print("산출물 변경이 없어 게시를 생략합니다.")
            return 0
        git(repo, "push", pub["remote"], f"{job['docs_commit']}:refs/heads/{pub['branch']}")
        phase("deploy")
    timeout = int(pub.get("timeout_sec", 900))
    if job["phase"] == "deploy":
        if pub.get("deploy_command"):
            _hook(pub["deploy_command"], repo, job, out, timeout)
        phase("verify")
    if job["phase"] == "verify":
        _hook(pub["verify_command"], repo, job, out, timeout)
        state["last_published"] = {k: job[k] for k in ("target", "docs_commit", "build_id")}
        state.pop("pending")
        state.pop("error", None)
        save(path, state)
        print(f"게시 확인 완료: {job['target']} ({job['build_id']})")
    return 0
