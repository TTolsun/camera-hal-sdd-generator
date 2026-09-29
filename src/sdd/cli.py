"""`sdd` CLI.

  sdd doctor                      도구, compile DB, LLM 도달 여부 점검
  sdd compdb [--regenerate|--normalize]   compile_commands.json 확보·정규화
  sdd extract [--skip-comments]    facts.json 생성 (clang-uml + libclang 주석 + flags)
  sdd impact --base <ref>         git diff 로 영향 섹션 계산 -> build/impact.json
  sdd generate [--sections a,b] [--from-impact]   SDD Markdown 생성
  sdd accept [문서...] [--finding 키]   사람 검토 승인을 장부에 기록
  sdd run --base <ref>            extract -> impact -> generate 한 번에
  sdd update [--to ref]           새 커밋을 차례로 증분 갱신 (관문에서 멈춤, 게시 없음)
  sdd build                       mkdocs build
  sdd export-site [--out dir]     탐색 메뉴·검색·Mermaid 확대를 갖춘 정적 사이트
  sdd fetch-mermaid               Mermaid ESM 배포본을 사내·오프라인 자산으로 준비
  sdd export-html [--out f.html]  SDD 전체를 파일 하나짜리 HTML 로
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from . import approvals as approvals_mod, compdb, extract, impact as impact_mod
from .carryover import carry_forward
from .config import Config, load
from .document_metadata import generation_method
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent, AgentError
from .impact_review import review_markdown
from .source_git import changed_files, resolve_commit


def _cfg(args: argparse.Namespace) -> Config:
    return load(Path(args.config).resolve() if args.config else None)


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    ok = True

    def line(label: str, good: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"[{'OK' if good else '!!'}] {label}: {detail}")

    line("소스 루트", cfg.source_root.exists(), cfg.source_root.as_posix())
    line("git", (cfg.source_root / ".git").exists(), "소스 루트가 git 저장소인지")
    line("compile DB", cfg.compile_commands.exists(),
         cfg.compile_commands.as_posix() + ("" if cfg.compile_commands.exists() else "  (sdd compdb 로 생성)"))
    # clang-uml 은 없어도 libclang 대체 분석으로 동작하므로 경고만 남긴다 (관계·다이어그램 일부가 빠진다).
    uml = shutil.which(cfg.clang_uml_bin)
    print(f"[{'OK' if uml else '..'}] clang-uml: {uml or f'{cfg.clang_uml_bin} 없음. libclang 대체 분석으로 동작 (템플릿 관계, include 그래프 제외)'}")
    # ndk-build 는 그 경로로 compile DB 를 만들 때만 필요하다. Soong/CMake 등 다른 빌드가 만든
    # DB 를 쓰는 프로젝트에서 이 점검이 항상 실패하면 안 된다.
    if cfg.ndk_build.get("enabled"):
        path = shutil.which("ndk-build")
        line("ndk-build", path is not None, path or "ndk-build 를 PATH 에서 찾지 못함")
    try:
        line("agent", True, Agent(cfg.agent).ping())
    except AgentError as e:
        line("agent", False, str(e))
    if cfg.compile_commands.exists():
        for w in compdb.check(compdb.load_entries(cfg.compile_commands)):
            print(f"[..] compile DB 경고: {w}")
    return 0 if ok else 1


def cmd_compdb(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    if args.normalize:
        import json
        source = Path(args.normalize_input).resolve() if args.normalize_input else cfg.compile_commands
        entries = compdb.load_entries(source)
        resource = compdb.clang_resource_dir(args.clang) if args.clang else None
        normalized = compdb.normalize(entries, resource)
        out = Path(args.out).resolve() if args.out else cfg.compile_commands
        if out == source and not args.out:
            # 원본 DB 를 조용히 덮어쓰지 않는다. 빌드 시스템이 다시 만들면 정규화가 사라지므로
            # 정규화본은 별도 파일로 두고 source.compile_commands 가 그 파일을 가리키게 한다.
            out = source.with_name(source.stem + ".normalized.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(normalized, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"정규화한 compile DB: {out} (TU {len(normalized)} 개"
              + (f", resource-dir {resource}" if resource else ", resource-dir 미지정") + ")")
        if not resource:
            print("clang 내장 헤더가 필요하면 --clang <clang 실행 파일> 을 지정하세요 (pip libclang 휠에는 없습니다).")
        for w in compdb.check(normalized):
            print(f"경고: {w}")
        return 0
    path = compdb.ensure(cfg, regenerate=args.regenerate)
    entries = compdb.load_entries(path)
    print(f"compile DB: {path} (TU {len(entries)} 개, -D {len(compdb.defines(entries))} 개)")
    for w in compdb.check(entries):
        print(f"경고: {w}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = extract.run(cfg, skip_comments=args.skip_comments, skip_clang_uml=args.skip_clang_uml,
                        only_diagrams=args.only.split(",") if args.only else None)
    print(f"facts: {cfg.facts_path} (클래스 {len(model.classes)}, 시나리오 {len(model.scenarios)}, "
          f"플래그 {len(model.defines)})")
    return 0


def _load_model(cfg: Config) -> KnowledgeModel:
    if not cfg.facts_path.exists():
        print("facts.json 이 없습니다. 먼저 `sdd extract` 를 실행하세요.", file=sys.stderr)
        raise SystemExit(2)
    return KnowledgeModel.load(cfg.facts_path)


def cmd_impact(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = _load_model(cfg)
    base, head = (resolve_commit(cfg.source_root, ref) for ref in (args.base, args.head))
    if model.meta.get("source_commit") != head:
        raise RuntimeError("현재 facts의 source_commit이 --head와 다릅니다. 대상 커밋에서 extract를 다시 실행하세요.")
    base_model = KnowledgeModel.load(Path(args.base_facts)) if args.base_facts else None
    if base_model and base_model.meta.get("source_commit") != base:
        raise RuntimeError("--base-facts의 source_commit이 --base와 다릅니다.")
    files = changed_files(cfg.source_root, base, head)
    report = impact_mod.compute(cfg, model, files, base, head, base_model)
    out = cfg.build_dir / "impact.json"
    report.save(out)
    ledger = approvals_mod.load(cfg)
    review = cfg.build_dir / "impact-review.md"
    review.write_text(review_markdown(report, ledger), encoding="utf-8", newline="\n")
    print(f"변경 파일 {len(files)} 개, 영향 섹션 {sorted(report.sections)}, 시나리오 {sorted(report.scenarios)}")
    print(f"-> {out}")
    open_items = approvals_mod.open_findings(report.coverage, ledger)
    accepted = len(report.coverage["findings"]) - len(open_items)
    print(f"문서 범위: {report.coverage['status']}, 검토 항목 {len(report.coverage['findings'])}개"
          + (f" (장부에서 승인된 {accepted}개 제외, 미결 {len(open_items)}개)" if accepted else "")
          + f" -> {review}")
    if not base_model:
        print("이전 facts 미제공: 삭제된 심볼의 범위 검사는 제한됩니다. --base-facts를 사용할 수 있습니다.")
    return 2 if args.fail_on_coverage_gap and open_items else 0


def _reviewer_name(cfg: Config, given: str | None) -> str:
    if given:
        return given
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True,
                              cwd=cfg.root).stdout.strip()
    except OSError:
        name = ""
    if not name:
        raise RuntimeError("승인자 이름을 알 수 없습니다. --by <이름> 으로 지정하세요.")
    return name


def cmd_accept(args: argparse.Namespace) -> int:
    """사람 검토 승인을 장부에 기록한다. 파이프라인은 이 명령을 자동으로 실행하지 않는다."""
    cfg = _cfg(args)
    ledger = approvals_mod.load(cfg)
    pages = [p for chunk in (args.pages or []) for p in chunk.split(",") if p]
    findings = [f for chunk in (args.finding or []) for f in chunk.split(",") if f]
    if not pages and not findings:
        print(f"승인 장부: {approvals_mod.ledger_path(cfg)}")
        print("", "## 문서", sep="\n")
        for path in sorted(cfg.sdd_dir.rglob("*.md")):
            rel = path.relative_to(cfg.sdd_dir).as_posix()
            text = path.read_text(encoding="utf-8")
            state = approvals_mod.page_status(ledger, rel, text)
            entry = ledger["pages"].get(rel, {})
            detail = {"approved": f"승인: {entry.get('approved_by')} {entry.get('approved_at', '')}",
                      "stale": f"승인 이후 본문 변경 (승인: {entry.get('approved_by')} {entry.get('approved_at', '')})",
                      "unreviewed": "사람 검토 전"}[state]
            print(f"- {rel}: {detail}")
        if ledger["findings"]:
            print("", "## 범위 검토 항목", sep="\n")
            for key, entry in sorted(ledger["findings"].items()):
                print(f"- {key}: {entry['state']} ({entry.get('by')} {entry.get('at', '')})")
        print("\n승인: sdd accept <문서.md> [--by 이름], 범위 항목: sdd accept --finding <키> [--defer]")
        return 0
    from .export_html import _split
    by = _reviewer_name(cfg, args.by)
    for rel in pages:
        # 장부 키는 사이트·이월과 같은 posix 상대 경로여야 한다. Windows 백슬래시나 ./ 가
        # 섞인 입력을 그대로 저장하면 승인이 영원히 일치하지 않는다.
        rel = str(PurePosixPath(rel.replace("\\", "/")))
        path = cfg.sdd_dir / rel
        if not path.is_file():
            raise RuntimeError(f"승인할 문서가 없습니다: {rel} (sdd_dir 기준 상대 경로)")
        text = path.read_text(encoding="utf-8")
        meta, _ = _split(text)
        entry = approvals_mod.approve_page(ledger, rel, text, by,
                                           source_commit=str(meta.get("source_commit", "")),
                                           note=args.note or "")
        if str(meta.get("status", "")) == "needs-review":
            print(f"주의: {rel} 은 자동 검사 확인 필요(needs-review) 상태입니다. 검토 후 승인했는지 확인하세요.")
        print(f"승인 기록: {rel} ({by}, {entry['approved_at']})")
    state = "deferred" if args.defer else "accepted"
    for key in findings:
        approvals_mod.record_finding(ledger, key, state, by, note=args.note or "")
        print(f"범위 검토 항목 {state}: {key} ({by})")
        if state == "deferred":
            print("  보류는 관문(--fail-on-coverage-gap)을 통과시키지 않습니다. 범위를 정리한 뒤 accepted 로 바꾸세요.")
    approvals_mod.save(cfg, ledger)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = _load_model(cfg)
    if any(s.get("design_topics") for s in cfg.sections()):
        from .evidence import collect as collect_evidence
        collect_evidence(cfg, model)
        model.save(cfg.facts_path)
    report = None
    if args.from_impact:
        p = cfg.build_dir / "impact.json"
        if not p.exists():
            print("build/impact.json 이 없습니다. 먼저 `sdd impact --base <ref>` 를 실행하세요.", file=sys.stderr)
            return 2
        report = impact_mod.ImpactReport.load(p)
        if report.coverage.get("findings"):
            print(f"문서 범위 검토 {len(report.coverage['findings'])}개가 남아 있습니다. build/impact-review.md를 확인하세요.")
    agent = Agent(cfg.agent, dump_dir=cfg.build_dir / "prompts")
    gen = Generator(cfg, model, agent)
    written = gen.run(section_ids=args.sections.split(",") if args.sections else None, impact=report)
    for w in written:
        print(f"-> {w.relative_to(cfg.root).as_posix()}")
    if report:
        # 영향 밖 원고는 LLM 없이 근거만 재검증해 새 커밋으로 이월한다. 어긋난 원고는 승격하지 않는다.
        promoted, stale = carry_forward(cfg, model, written)
        for pth in promoted:
            print(f"== {pth.relative_to(cfg.root).as_posix()} (영향 없음: 근거 재검증 후 커밋 이월)")
        for pth, invalid in stale:
            print(f"경고: {pth.relative_to(cfg.root).as_posix()} 의 인용 {len(invalid)}개가 새 facts 에 없습니다"
                  f" ({', '.join(invalid[:3])}). 이 섹션을 다시 생성해야 사이트를 게시할 수 있습니다.")
    if report:
        selected = set(args.sections.split(",")) if args.sections else set(report.sections)
        needs_llm = any(generation_method(s, cfg.agent.kind) in ("facts-and-llm", "mixed")
                        for s in cfg.sections() if s["id"] in report.sections and s["id"] in selected)
        summary = impact_mod.summary_facts(report, model)
        if needs_llm:
            summary = agent.chat((cfg.prompts_dir / "system.md").read_text(encoding="utf-8"),
                                 (cfg.prompts_dir / "change_impact.md").read_text(encoding="utf-8")
                                 .format(facts=summary), tag="change_impact")
        else:
            summary = "# 변경 영향 요약\n\n추출 사실과 영향 보고서로 구성한 요약입니다.\n\n" + summary
        (cfg.build_dir / "change_impact.md").write_text(summary + "\n", encoding="utf-8")
        print("-> build/change_impact.md (리뷰어용 변경 요약)")
    if (cfg.raw.get("site") or {}).get("enabled", False):
        from .export_site import export_site
        print(f"-> {export_site(cfg)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    rc = cmd_extract(args)
    if rc:
        return rc
    if args.base:
        rc = cmd_impact(args)
        if rc:
            return rc
        args.from_impact = True
    else:
        args.from_impact = False
    args.sections = None
    return cmd_generate(args)


def cmd_update(args: argparse.Namespace) -> int:
    from . import update as update_mod

    cfg = _cfg(args)

    def once() -> int:
        return update_mod.run_update(cfg, to=args.to, max_count=args.max, fetch=args.fetch).exit_code

    if not args.watch:
        return once()
    import time
    while True:
        rc = once()
        if rc:
            # 관문이나 실패에서 조용히 계속 돌면 사람이 멈춘 사실을 놓친다. 종료해서 드러낸다.
            return rc
        time.sleep(args.poll)


def cmd_build(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    return subprocess.run(["mkdocs", "build", "--strict"], cwd=cfg.root).returncode


def cmd_fetch_mermaid(args: argparse.Namespace) -> int:
    from . import mermaid_assets

    cfg = _cfg(args)
    dest = Path(args.dest).resolve() if args.dest else cfg.root / "assets" / "mermaid"
    written = mermaid_assets.fetch(dest, version=args.mermaid_version or mermaid_assets.DEFAULT_VERSION,
                                   registry=args.registry or mermaid_assets.DEFAULT_REGISTRY,
                                   tarball=Path(args.tarball).resolve() if args.tarball else None)
    print(f"Mermaid ESM {len(written)} 개 파일 -> {dest}")
    print("sdd.yaml 에 다음을 두면 사이트가 이 사본을 동봉합니다 (CDN 을 쓰지 않습니다).")
    try:
        rel = dest.relative_to(cfg.root).as_posix()
    except ValueError:
        rel = dest.as_posix()
    print(f"site:\n  mermaid_dir: {rel}")
    return 0


def cmd_export_html(args: argparse.Namespace) -> int:
    from .export_html import export

    cfg = _cfg(args)
    site = cfg.raw.get("site") or {}
    mermaid = args.mermaid or str(site.get("mermaid") or "") or None
    if not mermaid and site.get("mermaid_dir"):
        # 사이트와 같은 오프라인 구성을 따른다. fetch-mermaid 가 준비한 로컬 사본을 가리키면
        # CDN 없이도 단일 HTML 의 그림이 렌더링된다 (HTML 을 이 경로에서 읽을 수 있는 환경 기준).
        mermaid = (cfg.root / str(site["mermaid_dir"]) / "mermaid.esm.min.mjs").as_posix()
    out = export(cfg, out=Path(args.out).resolve() if args.out else None,
                 mkdocs_yml=Path(args.mkdocs).resolve() if args.mkdocs else None,
                 **({"mermaid_src": mermaid} if mermaid else {}), site_name=args.title,
                 pages=args.pages.split(",") if args.pages else None)
    print(f"-> {out}")
    return 0


def cmd_export_site(args: argparse.Namespace) -> int:
    from .export_site import export_site

    out = export_site(_cfg(args), out=Path(args.out).resolve() if args.out else None,
                      mermaid_src=args.mermaid)
    print(f"-> {out}")
    return 0


def cmd_verify_site(args: argparse.Namespace) -> int:
    from .site_build import verify_site
    cfg = _cfg(args)
    print(verify_site(Path(args.out) if args.out else cfg.build_dir / "site"))
    return 0


def cmd_automate(args: argparse.Namespace) -> int:
    from . import automation
    cfg = _cfg(args)
    if args.cron:
        config_path = Path(args.config).resolve() if args.config else cfg.root / "sdd.yaml"
        print(automation.cron(cfg, config_path), end="")
        return 0
    return automation.run(cfg)


def cmd_verify_publication(args: argparse.Namespace) -> int:
    import os
    from .publication import verify_remote
    site = args.site or os.environ.get("SDD_SITE_DIR")
    if not site:
        raise ValueError("--site 또는 SDD_SITE_DIR이 필요합니다.")
    print(verify_remote(Path(site), args.url, timeout=args.timeout, interval=args.interval))
    return 0


def cmd_improve(args: argparse.Namespace) -> int:
    import json
    import uuid
    from .automation import locked
    from .idle_review import run
    cfg = _cfg(args)
    with locked(cfg.build_dir / "automation.lock"):
        state_path = cfg.build_dir / "idle-review-state.json"
        previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if (cfg.build_dir / "automation-state.json").exists():
            publication = json.loads((cfg.build_dir / "automation-state.json").read_text(encoding="utf-8"))
            if publication.get("pending"):
                raise RuntimeError("진행 중인 게시가 있습니다. sdd automate로 먼저 재개하세요.")
        target = str(_load_model(cfg).meta.get("source_commit", ""))
        job = previous.get("pending", {}).get("job") or uuid.uuid4().hex
        result = run(cfg, target, job)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["status"] == "deferred" else 0


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔의 기본 코드 페이지(cp949)에서도 한국어 메시지가 깨지지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="sdd", description="Camera HAL SDD 자동 생성 파이프라인")
    p.add_argument("--config", help="설정 파일 경로. 이름은 sdd.yaml 이 아니어도 된다 "
                   "(기본: 현재 디렉터리에서 위로 sdd.yaml 탐색). 로컬 덮어쓰기는 같은 이름의 .local.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    s = sub.add_parser("compdb", help="compile DB 확보와 정규화")
    s.add_argument("--regenerate", action="store_true")
    s.add_argument("--normalize", action="store_true",
                   help="빌드 시스템(Meson/Soong/CMake)이 만든 DB 의 상대 경로를 절대 경로로 바꾸고 "
                        "-working-directory 를 채운다")
    s.add_argument("--normalize-input", help="정규화할 원본 DB (기본: source.compile_commands)")
    s.add_argument("--clang", help="내장 헤더를 가져올 clang 실행 파일. 지정하면 -resource-dir 를 채운다")
    s.add_argument("--out", help="정규화 결과 파일 (기본: 원본 옆의 *.normalized.json)")
    s.set_defaults(fn=cmd_compdb)

    s = sub.add_parser("extract")
    s.add_argument("--skip-comments", action="store_true")
    s.add_argument("--skip-clang-uml", action="store_true")
    s.add_argument("--only", help="clang-uml 다이어그램 이름을 쉼표로 나열 (예: class_overview,seq_flush)")
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("impact")
    s.add_argument("--base", required=True, help="비교 기준 commit/ref (예: HEAD~1, origin/main)")
    s.add_argument("--head", default="HEAD")
    s.add_argument("--base-facts", help="삭제·이름 변경 검토에 사용할 이전 커밋의 facts.json")
    s.add_argument("--fail-on-coverage-gap", action="store_true", help="범위 검토 항목을 기록한 뒤 종료 코드 2로 중단")
    s.set_defaults(fn=cmd_impact)

    s = sub.add_parser("generate")
    s.add_argument("--sections", help="섹션 id 를 쉼표로 나열. 생략하면 전체")
    s.add_argument("--from-impact", action="store_true", help="build/impact.json 의 섹션만 재생성")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("accept", help="사람 검토 승인을 장부(sdd/approvals.json)에 기록한다. 인자 없이 실행하면 상태를 보여 준다")
    s.add_argument("pages", nargs="*", help="승인할 문서 (sdd_dir 기준 상대 경로, 쉼표 나열 가능)")
    s.add_argument("--finding", action="append", help="승인·보류할 범위 검토 항목 키 (build/impact-review.md 에 표시)")
    s.add_argument("--defer", action="store_true", help="--finding 을 승인 대신 보류(deferred)로 기록")
    s.add_argument("--by", help="승인자 이름 (기본: git user.name)")
    s.add_argument("--note", help="승인 기록에 남길 메모")
    s.set_defaults(fn=cmd_accept)

    s = sub.add_parser("run")
    s.add_argument("--base", help="주면 impact 기반으로 영향 섹션만, 없으면 전체 생성")
    s.add_argument("--head", default="HEAD")
    s.add_argument("--base-facts", help="이전 커밋의 facts.json")
    s.add_argument("--fail-on-coverage-gap", action="store_true", help="범위 검토 항목이 있으면 생성 전에 중단")
    s.add_argument("--skip-comments", action="store_true")
    s.add_argument("--skip-clang-uml", action="store_true")
    s.add_argument("--only", default=None)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("update", help="기준 커밋 이후의 새 커밋을 오래된 것부터 하나씩 추출·영향 분석·생성한다. "
                                      "범위 검토 항목과 needs-review 관문에서 멈추며, 사이트는 게시하지 않는다")
    s.add_argument("--to", default="HEAD", help="따라갈 ref (기본: HEAD. 예: origin/main)")
    s.add_argument("--max", type=int, help="이번 실행에서 처리할 최대 커밋 수")
    s.add_argument("--fetch", action="store_true", help="시작 전에 git fetch 를 실행")
    s.add_argument("--watch", action="store_true", help="새 커밋을 주기적으로 확인하며 계속 실행 (관문·실패 시 종료)")
    s.add_argument("--poll", type=int, default=300, help="--watch 의 확인 간격 초 (기본: 300)")
    s.set_defaults(fn=cmd_update)

    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("improve", help="현재 facts 커밋에서 누락 한 항목을 점검·검증하여 보완 (Git 게시 없음)").set_defaults(fn=cmd_improve)

    s = sub.add_parser("automate", help="Hermes 설명 검토·증분 갱신·Git 반영·배포 확인을 재개 가능한 작업으로 실행")
    s.add_argument("--cron", action="store_true", help="설정한 시간·시간대의 crontab 내용을 출력 (설치하지 않음)")
    s.set_defaults(fn=cmd_automate)

    s = sub.add_parser("verify-publication", help="실제 URL의 manifest와 모든 산출물 해시가 로컬 사이트와 일치할 때까지 확인")
    s.add_argument("--url", required=True)
    s.add_argument("--site", help="로컬 사이트 (기본: SDD_SITE_DIR)")
    s.add_argument("--timeout", type=int, default=600)
    s.add_argument("--interval", type=int, default=10)
    s.set_defaults(fn=cmd_verify_publication)

    s = sub.add_parser("export-site", help="탐색 메뉴, 목차, 검색, Mermaid 확대를 갖춘 정적 문서 사이트")
    s.add_argument("--out", help="출력 디렉터리 (기본: build/site)")
    s.add_argument("--mermaid", help="Mermaid ESM URL 또는 사이트 루트 기준 로컬 경로")
    s.set_defaults(fn=cmd_export_site)

    s = sub.add_parser("verify-site", help="사이트 산출물 해시와 내부 링크를 검사한다")
    s.add_argument("--out", help="검사할 사이트 디렉터리 (기본: build/site)")
    s.set_defaults(fn=cmd_verify_site)

    s = sub.add_parser("fetch-mermaid", help="Mermaid ESM 배포본(본체 + chunk)을 받아 사내·오프라인 자산으로 둔다")
    s.add_argument("--dest", help="놓을 디렉터리 (기본: <설정 루트>/assets/mermaid)")
    s.add_argument("--mermaid-version", default=None, help="Mermaid 버전 (기본: 사이트 기본값과 같은 버전)")
    s.add_argument("--registry", default=None, help="npm 레지스트리 주소 (사내 미러를 지정할 수 있다)")
    s.add_argument("--tarball", help="미리 반입한 mermaid-<버전>.tgz 파일. 지정하면 내려받지 않는다")
    s.set_defaults(fn=cmd_fetch_mermaid)

    s = sub.add_parser("export-html", help="SDD 전체를 파일 하나짜리 HTML 로 만든다 (메일, 오프라인 열람용)")
    s.add_argument("--out", help="출력 파일 (기본: build/sdd.html)")
    s.add_argument("--mkdocs", help="페이지 순서를 가져올 mkdocs.yml (기본: 저장소 루트)")
    s.add_argument("--mermaid", default=None,
                   help="Mermaid ESM 경로 (기본: site.mermaid 설정, 없으면 공개 CDN). "
                        "사내망에서 CDN 이 막히면 로컬 파일 경로를 준다")
    s.add_argument("--title", default="Camera HAL SDD")
    s.add_argument("--pages", help="담을 페이지를 쉼표로 나열 (예: overview.md,scenarios/flush.md). 생략하면 전체")
    s.set_defaults(fn=cmd_export_html)

    args = p.parse_args(argv)
    if args.cmd == "run" and not args.base and (args.base_facts or args.fail_on_coverage_gap):
        p.error("run의 --base-facts와 --fail-on-coverage-gap에는 --base가 필요합니다.")
    try:
        return int(args.fn(args))
    except (AgentError, FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
