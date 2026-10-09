"""커밋 감시와 증분 자동 갱신: 새 커밋을 순서대로 처리하고, 사람 리뷰 관문에서 멈춘다.

큐와 순서는 저장하지 않고 매번 Git 에서 다시 계산한다. 마지막으로 끝낸 커밋(last_done)만
기록하면, 처리 순서는 `git rev-list --reverse` 가 보장하고, 실패한 커밋은 last_done 이
앞으로 가지 않으므로 다음 실행이 같은 커밋부터 다시 시작한다. 실패를 조용히 건너뛰는
경로가 없다.

관문 두 개에서 멈춘다. 어느 쪽도 자동으로 통과시키지 않는다.
1. 범위 검토 항목: 장부(sdd/approvals.json)에서 승인되지 않은 항목이 있으면 생성 전에 멈춘다.
2. 자동 검사: 생성 결과에 `status: needs-review` 페이지가 남으면 다음 커밋으로 가지 않는다.

이 명령은 사이트를 게시하지 않는다. 게시는 사람이 검토·승인한 뒤 export-site 로 한다.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import approvals as approvals_mod, extract, impact as impact_mod, source_git
from .carryover import carry_forward
from .config import Config, section_output
from .facts.model import KnowledgeModel
from .impact_review import review_markdown


def state_path(cfg: Config) -> Path:
    return cfg.build_dir / "update-state.json"


def load_state(cfg: Config) -> dict[str, Any]:
    path = state_path(cfg)
    if not path.exists():
        return {"schema": 1, "last_done": "", "failed": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise RuntimeError(f"지원하지 않는 갱신 상태 schema 입니다: {path}")
    data.setdefault("last_done", "")
    data.setdefault("failed", {})
    return data


def save_state(cfg: Config, state: dict[str, Any]) -> None:
    path = state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _baseline(cfg: Config, state: dict[str, Any]) -> str:
    """증분의 기준 커밋. 상태 파일이 비어 있으면 현재 facts 의 커밋에서 시작한다.

    첫 실행이 기준을 상태 파일에 적어 두므로, 도중에 실패해 facts.json 이 대상 커밋으로
    덮인 뒤 재시도해도 기준이 대상 커밋으로 밀리지 않는다.
    """
    if state.get("last_done"):
        return str(state["last_done"])
    if state.get("baseline"):
        return str(state["baseline"])
    if cfg.facts_path.exists():
        commit = str(KnowledgeModel.load(cfg.facts_path).meta.get("source_commit") or "")
        if commit:
            return commit
    raise RuntimeError("기준 커밋이 없습니다. 먼저 기준 커밋에서 `sdd extract` 로 전체를 추출하거나, "
                       "전체 생성(`sdd run`) 후 다시 실행하세요.")


def _needs_review_pages(cfg: Config, ledger: dict[str, Any]) -> list[str]:
    """자동 검사 확인 필요 상태이면서 사람 승인도 없는 페이지. 이 목록이 리뷰 관문을 막는다.

    승인 장부에 기록된(approved) 페이지는 사람이 needs-review 내용을 검토했다는 뜻이므로
    관문에서 제외한다. 본문이 바뀌면 승인이 stale 이 되어 다시 관문에 걸린다.
    """
    from .export_html import _split
    pages = []
    for section in cfg.sections():
        if section.get("kind") == "manual":
            continue
        rel = section_output(section)
        path = cfg.sdd_dir / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if (str(_split(text)[0].get("status", "")) == "needs-review"
                and approvals_mod.page_status(ledger, rel, text) != "approved"):
            pages.append(rel)
    return sorted(set(pages))


def _default_generate(cfg: Config, model: KnowledgeModel, report: impact_mod.ImpactReport) -> None:
    """cmd_generate 의 핵심만 수행한다: 설계 근거 수집, 영향 섹션 생성, 영향 밖 원고 이월.

    사이트 빌드와 변경 요약은 부르지 않는다. 게시는 사람 검토 뒤의 별도 단계다.
    """
    from .generate import Generator
    from .llm import Agent

    if any(s.get("design_topics") for s in cfg.sections()):
        from .evidence import collect as collect_evidence
        collect_evidence(cfg, model)
        model.save(cfg.facts_path)
    agent = Agent(cfg.agent, dump_dir=cfg.build_dir / "prompts")
    written = Generator(cfg, model, agent).run(impact=report)
    promoted, stale = carry_forward(cfg, model, written)
    if stale:
        names = ", ".join(p.relative_to(cfg.root).as_posix() for p, _ in stale)
        raise RuntimeError(f"이월하지 못한 원고가 있습니다 (인용이 새 facts 에 없음): {names}. "
                           "해당 섹션을 재생성 범위에 넣어야 합니다.")


@dataclass
class Steps:
    """한 커밋을 처리하는 단계. 테스트와 환경별 교체를 위해 주입할 수 있다."""
    checkout: Callable[[Config, str], None] = lambda cfg, sha: source_git.checkout(cfg.source_root, sha)
    prepare_compdb: Callable[[Config, str], None] = lambda cfg, sha: _run_compdb_cmd(cfg)
    extract: Callable[[Config], KnowledgeModel] = lambda cfg: extract.run(cfg)
    generate: Callable[[Config, KnowledgeModel, impact_mod.ImpactReport], None] = _default_generate


def _run_compdb_cmd(cfg: Config) -> None:
    """update.compdb_cmd 설정이 있으면 소스 루트에서 실행해 compile DB 를 새로 만든다.

    빌드 파일이 바뀐 커밋에서 낡은 DB 로 추출하면 사실이 어긋난다. 명령이 없으면 기존 DB 를
    그대로 쓰므로, 빌드 구성이 자주 바뀌는 저장소는 이 설정을 두어야 한다.
    """
    import subprocess
    cmd = (cfg.raw.get("update", {}) or {}).get("compdb_cmd")
    if cmd:
        subprocess.run([str(c) for c in cmd], cwd=cfg.source_root, check=True)


@dataclass
class Result:
    processed: list[str] = field(default_factory=list)
    stopped_reason: str = ""
    exit_code: int = 0


def run_update(cfg: Config, to: str = "HEAD", max_count: int | None = None,
               fetch: bool = False, steps: Steps | None = None,
               log: Callable[[str], None] = print) -> Result:
    steps = steps or Steps()
    result = Result()
    if not source_git.is_clean(cfg.source_root):
        raise RuntimeError(f"소스 저장소에 커밋되지 않은 변경이 있습니다: {cfg.source_root}. "
                           "자동 갱신은 소스를 체크아웃하며 진행하므로 먼저 정리해야 합니다.")
    if fetch:
        source_git.fetch(cfg.source_root)
    state = load_state(cfg)
    base = _baseline(cfg, state)
    if not state.get("last_done") and not state.get("baseline"):
        state["baseline"] = base
        save_state(cfg, state)
    if not source_git.is_ancestor(cfg.source_root, base, to):
        # rebase·force-push 로 기준이 이력에서 사라지면 base..to 가 재작성된 이력 전체를 돌려주고,
        # 그 diff 는 실제 변경이 아니다. 조용히 재처리하지 않고 사람이 기준을 다시 정하게 한다.
        raise RuntimeError(f"기준 커밋 {base[:12]} 이 {to} 의 조상이 아닙니다 (rebase 또는 force-push 추정). "
                           "기준을 다시 정하려면 대상 이력의 커밋에서 extract 를 수행하고 "
                           f"{state_path(cfg)} 를 삭제한 뒤 실행하세요.")
    queue = source_git.commits_between(cfg.source_root, base, to)
    if max_count is not None:
        queue = queue[:max_count]
    if not queue:
        from .document_health import enforce
        enforce(cfg)
        log(f"새 커밋이 없습니다 (기준: {base[:12]}).")
        return result
    log(f"처리할 커밋 {len(queue)} 개 (기준: {base[:12]})")
    ledger = approvals_mod.load(cfg)
    # 지난 실행이 남긴 needs-review 를 검토 없이 지나치지 못하게, 시작 시점에도 같은 관문을 세운다.
    pending_review = _needs_review_pages(cfg, ledger)
    if pending_review:
        result.stopped_reason = ("검토가 끝나지 않은 needs-review 페이지가 있어 시작하지 않습니다: "
                                 + ", ".join(pending_review)
                                 + ". 재생성으로 해소하거나, 검토를 마쳤다면 `sdd accept <문서>` 로 승인을 기록하세요.")
        result.exit_code = 3
        log(result.stopped_reason)
        return result
    # 처리 중에는 소스를 detached 로 체크아웃하므로, 끝나면 원래 브랜치로 되돌린다.
    # 되돌리지 않으면 다음 실행의 기본 대상(HEAD)이 브랜치 끝이 아니라 마지막으로
    # 체크아웃한 커밋을 가리켜, 그 뒤의 커밋을 조용히 놓친다.
    original_ref = source_git.current_ref(cfg.source_root)
    try:
        return _process_queue(cfg, queue, base, state, ledger, steps, result, log)
    finally:
        try:
            source_git.checkout_ref(cfg.source_root, original_ref)
        except Exception as e:                      # 복원 실패는 숨기지 않고 알린다
            log(f"경고: 소스를 {original_ref} 로 되돌리지 못했습니다: {e}")


def _process_queue(cfg: Config, queue: list[str], base: str, state: dict[str, Any],
                   ledger: dict[str, Any], steps: Steps, result: Result,
                   log: Callable[[str], None]) -> Result:
    for sha in queue:
        log(f"== {sha[:12]} 처리 시작")
        try:
            from . import document_health
            document_health.prepare(cfg)
            steps.checkout(cfg, sha)
            steps.prepare_compdb(cfg, sha)
            # 직전 커밋의 facts 를 비교 기준으로 보존한 뒤 새 facts 를 추출한다. 실패 후 재시도로
            # facts.json 이 이미 대상 커밋 것으로 덮여 있으면, 커밋이 어긋난 사본은 쓰지 않는다.
            base_model = None
            kept = cfg.build_dir / f"facts-{base[:12]}.json"
            if kept.exists():
                candidate = KnowledgeModel.load(kept)
                base_model = candidate if candidate.meta.get("source_commit") == base else None
            if base_model is None and cfg.facts_path.exists():
                current = KnowledgeModel.load(cfg.facts_path)
                if current.meta.get("source_commit") == base:
                    kept.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(cfg.facts_path, kept)
                    base_model = current
            if base_model is None:
                log(f"기준 {base[:12]} 의 facts 가 없어 삭제된 심볼 검사가 제한됩니다.")
            model = steps.extract(cfg)
            if model.meta.get("source_commit") != sha:
                raise RuntimeError("추출된 facts 의 source_commit 이 대상 커밋과 다릅니다. "
                                   "소스 체크아웃이 실제로 반영됐는지 확인하세요.")
            files = source_git.changed_files(cfg.source_root, base, sha)
            report = impact_mod.compute(cfg, model, files, base, sha, base_model)
            report.save(cfg.build_dir / "impact.json")
            (cfg.build_dir / "impact-review.md").write_text(review_markdown(report, ledger),
                                                            encoding="utf-8", newline="\n")
            open_items = approvals_mod.open_findings(report.coverage, ledger)
            if open_items:
                result.stopped_reason = (f"{sha[:12]}: 승인되지 않은 범위 검토 항목 {len(open_items)}개. "
                                         "build/impact-review.md 를 확인하고 sdd accept --finding 으로 "
                                         "처리한 뒤 다시 실행하세요.")
                result.exit_code = 2
                log(result.stopped_reason)
                return result
            steps.generate(cfg, model, report)
            health = document_health.enforce(cfg, model)
            if not _needs_review_pages(cfg, ledger):
                document_health.checkpoint(cfg, health)
            state["last_done"] = sha
            state["failed"].pop(sha, None)
            save_state(cfg, state)
            # 방금 소비한 기준 facts 사본은 더 쓰지 않는다. 남겨 두면 장기 운영에서 커밋 수만큼 쌓인다.
            kept.unlink(missing_ok=True)
            base = sha
            result.processed.append(sha)
            log(f"== {sha[:12]} 완료")
        except Exception as e:
            state["failed"][sha] = str(e)
            save_state(cfg, state)
            result.stopped_reason = f"{sha[:12]} 처리 실패: {e}. 다음 실행이 같은 커밋부터 재시도합니다."
            result.exit_code = 1
            log(result.stopped_reason)
            return result
        pending_review = _needs_review_pages(cfg, ledger)
        if pending_review:
            result.stopped_reason = (f"{sha[:12]} 생성 결과에 needs-review 페이지가 있습니다: "
                                     + ", ".join(pending_review)
                                     + ". 사람 검토 후 다음 커밋을 처리하세요.")
            result.exit_code = 3
            log(result.stopped_reason)
            return result
    log(f"완료: 커밋 {len(result.processed)} 개 처리. 게시는 검토·승인 후 export-site 로 진행하세요.")
    return result
