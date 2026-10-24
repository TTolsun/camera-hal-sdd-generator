"""SDD 페이지 생성.

페이지 뼈대(templates/page.md)는 style/README.md 규칙을 따른다.
  1. 할 일 또는 결론 한 문장(lead)  2. 확인할 내용 -> 절 표(routes)  3. 본문
  4. 근거와 검토 정보  5. 다음 단계 하나(next)

본문에서 표, 번호 목록, 다이어그램은 사실(facts)에서 파이프라인이 직접 만든다.
LLM 은 표만으로 알 수 없는 관계와 순서를 서술하는 문단만 쓴다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .budget import Block
from .config import Config, section_output
from .diagrams import diagram_block, section_diagram
from .document_metadata import generation_method
from .design_contracts import audit as audit_design
from .contract_render import coverage_table, SourceDetails
from .scenario_document import build as scenario_document, hidden_message, fingerprint as scenario_fingerprint
from .facts.model import ClassInfo, FunctionInfo, KnowledgeModel
from .impact import ImpactReport
from .matching import is_anonymous, matches_symbol, package_of, package_selected
from .narration import Narrator, ChatPort
from .page_writer import PageWriter
from .fact_presenter import FactPresenter
from .markdown_text import slugify
from .prompting import style_rules, compose_system_prompt
from .validate import Verdict, extract_citations
from .llm import AgentError
from . import generated_design
from .evidence import contract_text, fingerprint, requires_fingerprint, topic_blocks
from .semantic import relation_facts, structural_text

_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)


class Generator:
    def __init__(self, cfg: Config, model: KnowledgeModel, agent: ChatPort):
        self.cfg = cfg
        self.model = model
        self.agent = agent
        self.allowed = model.citations()
        self.reviews: dict[str, dict] = {}
        self.generated_designs: dict[str, tuple] = {}
        # routes 표의 링크 글자: 페이지 링크는 섹션 제목, 앵커 링크는 본문의 ## 제목 원문을 쓴다.
        self.page_titles = {sec.get("output", f"{sec['id']}.md"): sec["title"] for sec in cfg.sections()}
        self.page_titles.update({f"{sid}.md": sc.title for sid, sc in model.scenarios.items()})
        # scenarios.yaml 의 순서와 표시 규칙(hide)을 쓴다. 목차와 페이지 연결을 설정한 순서대로 두어야
        # 읽는 사람이 호출이 일어나는 차례대로 따라갈 수 있다.
        self.scenario_order = [sc["id"] for sc in cfg.scenarios()]
        self.scenario_cfg = {sc["id"]: sc for sc in cfg.scenarios()}
        self.narrator = Narrator(cfg, model, agent, self._record_review)
        self.writer = PageWriter(cfg, model, self.page_titles)
        self.facts = FactPresenter(model, cfg.package_depth)


    # ---- 진입점 ------------------------------------------------------------

    def run(self, section_ids: list[str] | None = None, impact: ImpactReport | None = None) -> list[Path]:
        written: list[Path] = []
        # Validate every selected contract before replacing any manuscript.
        selected = [s for s in self.cfg.sections()
                    if (not section_ids or s['id'] in section_ids) and (not impact or s['id'] in impact.sections)]
        reports = {s['id']: audit_design(self.model, s) for s in selected
                   if (s.get('design_requirements') or s.get('reader_profile')) and not generated_design.enabled(s)}
        # Generate and validate every required LLM answer before replacing any page.
        # Failed responses remain in the agent's prompt logs; old manuscripts survive.
        self.generated_designs = {}
        for sec in selected:
            if generated_design.enabled(sec):
                try:
                    section_diagram(self.cfg, self.model, sec)
                    self.generated_designs[sec['id']] = generated_design.generate(self, sec)
                    reports[sec['id']] = self.generated_designs[sec['id']][2]
                except (ValueError, AgentError) as exc:
                    reports[sec['id']] = {'status': 'incomplete', 'requirements': [],
                                          'findings': [str(exc)], 'human_review': 'pending'}
        if reports:
            self.cfg.build_dir.mkdir(parents=True, exist_ok=True)
            (self.cfg.build_dir / 'design-review.json').write_text(json.dumps(
                {'source_commit': self.model.meta.get('source_commit'), 'sections': reports},
                ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            problems = [f"{sid}: {note}" for sid, report in reports.items() for note in report['findings']]
            if problems:
                raise ValueError('설계 항목 검증 실패:\n' + '\n'.join(problems))
        for sec in self.cfg.sections():
            kind = sec.get("kind", "prose")
            if section_ids and sec["id"] not in section_ids:
                continue
            if impact and sec["id"] not in impact.sections:
                continue
            if kind == "manual":
                # 고른 섹션만 만들 때는 그 섹션의 자리만 만든다. 범위 밖 파일을 건드리지 않는다.
                stub = self._manual_stub(sec)
                if stub is not None:
                    written.append(stub)
                continue
            if kind == "prose":
                written.append(self._prose(sec))
            elif kind == "per-package":
                written.append(self._per_package(sec, impact))
            elif kind == "per-scenario":
                written += self._per_scenario(sec, impact)
            elif kind == "table":
                written.append(self._flags_table(sec))
            elif kind == "index":
                written.append(self._index_page(sec))
            else:
                raise ValueError(f"{sec['id']}: 알 수 없는 kind {kind}")
        return written

    # ---- 종류별 --------------------------------------------------------------

    def _prose(self, sec: dict[str, Any]) -> Path:
        original = sec
        evidence_model = self.model
        if generated_design.enabled(sec):
            evidence_model, sec, _, _ = self.generated_designs[sec['id']]
        # Validate diagram policy before spending a model call. Structure is never LLM output.
        diagram = diagram_block(section_diagram(self.cfg, self.model, sec))
        facts = sec.get("facts", {})
        tables: list[str] = []
        blocks: list[Block] = []

        if facts.get("packages"):
            t = self._package_table(facts["packages"])
            tables.append("## 패키지별 역할\n\n" + t)
            blocks.append(Block("packages", "### 패키지별 역할\n" + t, 0))
            deps = self._package_deps_table(facts["packages"])
            if deps:
                tables.append("## 패키지 사이의 의존\n\n" + deps)
                blocks.append(Block("package-deps", "### 패키지 사이의 의존\n" + deps, 1))
        if facts.get("functions"):
            t = self._entrypoint_table(facts["functions"])
            if t:
                tables.append("## 관련 자유 함수\n\n" + t)
                blocks.append(Block("functions", "### 관련 자유 함수\n" + t, 2))
        if facts.get("classes"):
            classes = [c for c in self._sorted_classes() if _match_class(c, sec)]
            missing_classes = [name for name in facts["classes"] if not any(ch in name for ch in "*?[")
                               and not any(matches_symbol(c.name, [name]) for c in classes)]
            if missing_classes:
                absence = "현재 facts에서 선택한 클래스가 추출되지 않았습니다: " + ", ".join(f"`{n}`" for n in missing_classes)
                tables.append("## 추출 범위 확인\n\n" + absence + ". 소스 전체에 없다는 판정은 아닙니다.")
                blocks.append(Block("missing-classes", absence, 1))
            if classes:
                # class_table: false 이면 표는 안 그리고 LLM 에게 인용할 사실만 준다 (개요처럼 표가 과한 절).
                if facts.get("class_table", True):
                    tables.append("## 관련 클래스\n\n" + _class_table(classes))
                blocks += [Block(f"class:{c.name}", _class_fact(c), 2) for c in classes]
                blocks.append(Block("relations", relation_facts(self.model, {c.name for c in classes}), 1))
        if facts.get("reading_order"):
            ro = self._reading_order(facts["reading_order"])
            if ro:
                tables.append("## 선택한 시나리오의 코드 읽기 순서\n\n" + ro)

        if sec.get("design_topics"):
            parts, omitted, verdict = [], [], Verdict(ok=True)
            sources = SourceDetails()
            for topic in sec["design_topics"]:
                evidence, gaps = topic_blocks(evidence_model, sec["id"], topic)
                topic_sec = {**sec, "answers": [topic["question"]], "semantic_review": True}
                tag = f"{sec['id']}_{topic['id']}"
                if gaps:
                    text = "확인 필요: " + " / ".join(gaps)
                    missing, current = [], Verdict(ok=False, notes=gaps)
                    self._record_review(tag, text, current, missing)
                elif "statements" in topic:
                    text, gaps = contract_text(evidence_model, sec["id"], topic)
                    missing, current = [], Verdict(ok=not gaps, notes=gaps)
                    self._record_review(tag, text, current, missing,
                                        mode="generated-prose" if generated_design.enabled(original) else "source-bound-contract")
                else:
                    text, missing, current = self._ask(tag, topic_sec, topic["title"], evidence, "")
                detail = sources.links(evidence_model, sec['id'], topic) if sec.get('show_evidence') and current.ok else ''
                parts.append(f"## {topic['title']}\n\n{text}" + (f"\n\n{detail}" if detail else ''))
                blocks += evidence
                omitted += missing
                if not current.ok:
                    verdict.ok = False
                    verdict.notes += current.notes
            if sec.get('design_requirements'):
                parts.append(coverage_table(evidence_model, sec))
            if sources.records:
                parts.append(sources.render())
            prose = "\n\n".join(parts)
        elif sec.get("narration") == "facts":
            selected = {c.name for c in self._sorted_classes() if _match_class(c, sec)}
            text = structural_text(self.model, selected)
            omitted = []
            verdict = Verdict(ok=bool(selected) and all(self.model.classes[n].loc for n in selected))
            if not verdict.ok:
                verdict.notes.append("설명할 클래스 또는 선언 근거가 없습니다.")
            self._record_review(sec['id'], text, verdict, omitted, mode="extracted-structure")
            prose = f"## {sec.get('prose_heading', '구조 설명')}\n\n{text}"
        else:
            text, omitted, verdict = self._ask(sec["id"], sec, sec["title"], blocks, self._existing(sec))
            prose = f"## {sec.get('prose_heading', '구조 설명')}\n\n{text}"
        body = "\n\n".join([prose]
                           + ([diagram] if diagram else []) + tables)
        if sec.get("needs_human"):
            body += "\n\n확인 필요: 이 절의 내용은 정적 분석 결과입니다. 콜백 실행 스레드와 종료 순서는 코드를 직접 실행해서 확인해야 합니다."
        return self._write_section(original, body, blocks, tables, verdict, omitted)

    def _per_package(self, sec: dict[str, Any], impact: ImpactReport | None) -> Path:
        parts: list[str] = []
        routes: list[tuple[str, str]] = []
        all_blocks: list[Block] = []
        all_tables: list[str] = []
        omitted_all: list[str] = []
        worst = Verdict(ok=True)
        existing = self._existing(sec)
        # 영향 밖 패키지의 기존 절은 지우지 않고 이월한다. 이월 조건은 절의 인용이 새 facts 에도
        # 전부 있는 것이고, 조건을 어기거나 기존 절이 없으면 그 패키지도 다시 생성한다.
        limit = set(impact.packages) if impact and impact.packages else None
        # Citation equality alone cannot preserve a semantically checked package.
        # Until per-package evidence fingerprints exist, regenerate its full page.
        if sec.get("semantic_review"):
            limit = None
        reusable = self._existing_blocks(sec) if limit is not None else {}

        diagram = self._diagram_ref(sec.get("facts", {}).get("diagram"))
        if diagram:
            parts.append("## 전체 구조도\n\n" + diagram)

        pkg_pats = sec.get("facts", {}).get("packages") or []
        # narration: facts 는 패키지별 클래스 표만 facts 에서 만든다. LLM 을 부르지 않고, 패키지마다
        # 달라지는 설명 문장도 만들지 않는다(번역 목록과 검토 대상이 패키지 수만큼 늘지 않게).
        facts_only = sec.get("narration") == "facts"
        functions: dict[str, list[FunctionInfo]] = {}
        if facts_only:
            pats = sec.get("facts", {}).get("functions") or []
            for f in self.model.functions.values():
                loc = f.loc or f.def_loc
                if loc and pats and matches_symbol(f.name, pats):
                    functions.setdefault(package_of(loc.file, self.cfg.package_depth), []).append(f)
        for pkg_name in sorted(set(self.model.packages) | set(functions)):
            if pkg_pats and not _pkg_selected(pkg_name, pkg_pats):
                continue
            classes = [self.model.classes[n] for n in self.model.packages[pkg_name].classes
                       if n in self.model.classes] if pkg_name in self.model.packages else []
            classes = [c for c in classes if _match_class(c, sec)]
            if facts_only:
                tables = []
                if classes:
                    tables.append(_class_table(sorted(classes, key=lambda c: c.name)))
                if functions.get(pkg_name):
                    tables.append(_function_table(sorted(functions[pkg_name], key=lambda f: f.name)))
                if not tables:
                    continue
                table = "\n\n".join(tables)
                parts.append(f"## {pkg_name}\n\n{table}")
                all_blocks.append(Block("table", f"### 패키지 {pkg_name}\n{table}", 0))
                all_tables.append(table)
                if not all(c.loc for c in classes):
                    worst = Verdict(ok=False, notes=[f"{pkg_name}: 선언 위치가 없는 클래스가 있습니다."])
                continue
            if not classes:
                continue
            if limit is not None and pkg_name not in limit:
                reused = reusable.get(pkg_name, "")
                if reused and all(c in self.allowed for c in extract_citations(reused)):
                    parts.append(reused.strip())
                    routes.append((f"{pkg_name} 패키지의 클래스를 수정합니다.", f"#{slugify(pkg_name)}"))
                    all_tables.append(reused)   # 페이지 근거 파일 목록에 이월 절의 인용도 남긴다.
                    continue
            table = _class_table(classes)
            blocks = [Block("table", f"### 패키지 {pkg_name}\n{table}", 0)]
            blocks += [Block(f"class:{c.name}", _class_fact(c), 1) for c in classes]
            text, omitted, verdict = self._ask(f"{sec['id']}_{slugify(pkg_name)}", sec,
                                               f"{sec['title']}: {pkg_name}", blocks, _subsection(existing, pkg_name))
            evidence = self._evidence_lines(blocks, [table], verdict, omitted)
            parts.append(f"## {pkg_name}\n\n{table}\n\n{text}\n\n??? note \"근거와 검토 정보: {pkg_name}\"\n{evidence}")
            routes.append((f"{pkg_name} 패키지의 클래스를 수정합니다.", f"#{slugify(pkg_name)}"))
            all_blocks += blocks
            all_tables.append(table)
            omitted_all += [f"{pkg_name}/{o}" for o in omitted]
            if not verdict.ok:
                worst = verdict

        if facts_only and not parts:
            worst = Verdict(ok=False, notes=["선택한 패키지에 클래스가 없습니다."])
        return self._write_section(sec, "\n\n".join(parts), all_blocks, all_tables, worst, omitted_all,
                                   routes=routes or None)

    def _per_scenario(self, sec: dict[str, Any], impact: ImpactReport | None) -> list[Path]:
        narration = sec.get("narration", "facts")
        if narration not in ("facts", "llm"):
            raise ValueError("시나리오 narration은 facts 또는 llm이어야 합니다.")
        out: list[Path] = []
        ordered = self._ordered_scenarios()
        rows = ["| 시나리오 | 진입점 | 요약 대상 호출 | 요약에서 뺀 호출 | 예약된 호출 | 미해결 호출 |",
                "|---|---|---|---|---|---|"]
        routes: list[tuple[str, str]] = []
        shown_by_id: dict[str, tuple[list[Any], int]] = {}
        policy = {**(self.cfg.raw.get("diagrams") or {}), **(sec.get("diagram") or {})}
        documents = {sid: scenario_document(sc, self.scenario_cfg.get(sid, {}), int(policy.get("max_nodes", 16)))
                     for sid, sc in ordered if not impact or sid in impact.scenarios}
        for sid, sc in ordered:
            shown, hidden = self._visible_messages(sc)
            shown_by_id[sid] = (shown, hidden)
            # index.md 와 같은 디렉터리에 있으므로 파일 이름만 쓴다.
            rows.append(f"| [{sc.title}]({sid}.md) | `{sc.entry}` | {len(shown)} | {hidden} "
                        f"| {sc.deferred} | {sc.unresolved} |")
            routes.append((f"{sc.title} 흐름을 추적합니다.", f"scenarios/{sid}.md"))

        for idx, (sid, sc) in enumerate(ordered):
            if impact and sid not in impact.scenarios:
                continue
            doc = documents[sid]
            blocks = [Block("steps", f"### 시나리오 {sc.title}\n- 진입점: {sc.entry}\n{doc.prompt}", 0)]
            if narration == "llm":
                # Paragraph-level evidence checks are required for optional prose.
                text, omitted, verdict = self._ask(f"scenario_{sid}", {**sec, "semantic_review": True}, sc.title, blocks, "")
            else:
                text, omitted = doc.introduction, []
                verdict = Verdict(ok=bool(sc.messages) and all(m.loc for m in sc.messages))
                if not verdict.ok:
                    verdict.notes.append("시나리오 호출 또는 근거 위치가 없습니다.")
                self._record_review(f"scenario_{sid}", text, verdict, omitted, mode="extracted-scenario")
            if omitted or not sc.messages:
                verdict.ok = False
                verdict.notes.append("시나리오 설명의 입력 근거가 비었거나 입력 예산에서 제외됐습니다.")
                self._record_review(f"scenario_{sid}", text, verdict, omitted)
            body_parts = [f"## 이 흐름에서 확인할 것\n\n{text}", doc.overview, doc.details]
            nxt = ordered[idx + 1][1] if idx + 1 < len(ordered) else None
            next_link = (nxt.title, f"scenarios/{nxt.id}.md") if nxt else ("핵심 시나리오 목록", "scenarios/index.md")
            path = self.cfg.sdd_dir / "scenarios" / f"{sid}.md"
            page = self._render(
                title=sc.title, lead=f"`{sc.entry}` 의 주요 호출과 추적 경계를 확인한 뒤 필요한 상세 기록을 펼쳐 보세요.",
                body="\n\n".join(body_parts), routes=_routes_from_headings("\n\n".join(body_parts)),
                evidence=self._evidence_lines(blocks, [doc.details], verdict, omitted),
                next_link=next_link, status=_status(verdict), omitted=omitted,
                extra={"section": sec["id"], "entry": sc.entry,
                       "scenario_id": sid,
                       "scenario_fingerprint": scenario_fingerprint(sc, self.scenario_cfg.get(sid, {})),
                       "generation_method": generation_method(sec, self.cfg.agent.kind)}, page_path=path)
            out.append(self._write(path, page))


        index_body = "## 시나리오 목록\n\n" + "\n".join(rows)
        # 시나리오가 하나도 없는 목차를 통과로 기록하면, 진입점 설정이 어긋난 상태가 문서에 드러나지 않는다.
        index_verdict = Verdict(ok=bool(ordered))
        if not ordered:
            missing = int((self.model.meta.get("callgraph") or {}).get("missing_entries", 0))
            reason = (f"설정한 진입 함수 {missing} 개를 추출에서 찾지 못했습니다."
                      if missing else "scenarios.yaml 에 진입 함수가 없거나 추출이 시나리오를 만들지 않았습니다.")
            index_verdict.notes.append(reason)
            index_body += ("\n\n확인 필요: 추적한 시나리오가 없습니다. " + reason
                           + " `sdd extract` 로그의 진입점 경고를 확인하고, `config/scenarios.yaml` 의"
                             " 시그니처를 대상 커밋의 정의와 대조해야 합니다.")
        missing_ids = [sid for sid in self.scenario_order if sid not in self.model.scenarios]
        if ordered and missing_ids:
            index_verdict.ok = False
            reason = "설정한 시나리오가 facts에 없습니다: " + ", ".join(missing_ids)
            index_verdict.notes.append(reason)
            index_body += "\n\n확인 필요: " + reason + ". 진입점과 추출 범위를 확인하세요."
        index_path = self.cfg.sdd_dir / sec.get("output", "scenarios/index.md")
        index_page = self._render(
            title=sec["title"], lead=sec.get("lead", ""), body=index_body, routes=routes,
            evidence=self._evidence_lines([], [], index_verdict, []),
            next_link=_next_of(sec), status=_status(index_verdict), omitted=[],
            extra={"section": sec["id"], "generation_method": "deterministic"}, page_path=index_path)
        out.append(self._write(index_path, index_page))
        return out

    def _manual_stub(self, sec: dict[str, Any]) -> Path | None:
        """사람이 쓰는 문서가 아직 없으면 빈 자리를 만든다. 이미 있으면 건드리지 않는다.

        설정에 있는 문서로 연결한 링크는 파일이 없으면 깨진다. 없는 채로 두면 사이트 빌드가
        멈추고, 링크를 지우면 써야 할 문서가 설정에서만 남아 잊힌다. 그래서 무엇을 써야 하는지
        적은 자리를 만들어 두고, 사람이 채우면 그 뒤로는 덮어쓰지 않는다.
        """
        path = self.cfg.sdd_dir / section_output(sec)
        if path.exists():
            return None
        body = ("## 아직 작성되지 않았습니다" + "\n\n"
                "이 문서는 파이프라인이 만들지 않습니다. 코드에서 확인할 수 없는 설계 결정과 기기 관찰을"
                " 사람이 적는 자리입니다." + "\n\n"
                "이 파일을 직접 편집하세요. 내용을 채우면 이후 생성에서 덮어쓰지 않습니다.")
        return self._write_section(sec, body, [], [], Verdict(ok=False, notes=["사람이 작성해야 하는 문서입니다."]), [])

    def _index_page(self, sec: dict[str, Any]) -> Path:
        """문서 목록 한 장. 설정의 문서 정의를 그대로 옮기므로 LLM 을 부르지 않는다.

        mkdocs 와 사이트 모두 첫 페이지로 `index.md` 를 찾는다. 파이프라인이 만들지 않으면
        섹션을 추가하거나 지울 때마다 사람이 따로 맞춰야 하고, 맞추지 않으면 첫 페이지가 비어 버린다.
        """
        rows = ["| 문서 | 읽는 사람 | 먼저 할 일 |", "|---|---|---|"]
        for other in self.cfg.sections():
            if other["id"] == sec["id"]:
                continue
            rel = section_output(other)
            # 사람이 쓰는 문서는 파이프라인이 만들지 않는다. 아직 없는 파일로 링크를 걸지 않는다.
            if other.get("kind") == "manual" and not (self.cfg.sdd_dir / rel).is_file():
                continue
            rows.append(f"| [{other['title']}]({rel}) | {other.get('reader', '확인 필요')} "
                        f"| {other.get('lead', '확인 필요')} |")
        body = ("## 문서 목록\n\n"
                "이 표는 문서 정의(`sections.yaml`)를 그대로 옮긴 것입니다. LLM 을 거치지 않았습니다.\n\n"
                + "\n".join(rows))
        return self._write_section(sec, body, [], [body], Verdict(ok=True), [])

    def _flags_table(self, sec: dict[str, Any]) -> Path:
        lines = ["## 플래그 표", "",
                 "이 표는 compile DB(NDK-build 구성)의 `-D` 목록과 소스의 `#if` 분기 위치를 그대로 옮긴 것입니다. LLM 을 거치지 않았습니다.",
                 "", "| 플래그 | 값 | 분기 위치 (최대 20) |", "|---|---|---|"]
        for name in sorted(self.model.defines):
            d = self.model.defines[name]
            sites = ", ".join(f"`{u.cite()}`" for u in d.usages) or "(소스에서 분기 없음)"
            lines.append(f"| `{name}` | `{d.value}` | {sites} |")
        body = "\n".join(lines)
        return self._write_section(sec, body, [], [body], Verdict(ok=True), [])

    # ---- LLM 호출 ------------------------------------------------------------

    def _ask(self, tag, sec, title, blocks, existing):
        return self.narrator.ask(tag, sec, title, blocks, existing)

    def _record_review(self, tag: str, text: str, verdict: Verdict, omitted: list[str], mode: str = "generated-prose") -> None:
        self.reviews[tag] = {"status": _status(verdict), "findings": verdict.notes,
                             "facts_omitted": omitted, "text": text,
                             "mode": mode,
                             "human_review": "pending",
                             "scope": "source-bound-contract: excerpt hash equality; extracted-structure: facts rendering; generated-prose: citation, manuscript and configured structural checks; no semantic approval"}
        path = self.cfg.build_dir / "content-review.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"source_commit": self.model.meta.get("source_commit"),
                                    "sections": self.reviews}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- 사실에서 만드는 표와 목록 -------------------------------------------------

    def _sorted_classes(self, *args, **kwargs):
        return self.facts._sorted_classes(*args, **kwargs)

    def _package_table(self, *args, **kwargs):
        return self.facts._package_table(*args, **kwargs)

    def _package_deps_table(self, *args, **kwargs):
        return self.facts._package_deps_table(*args, **kwargs)

    def _entrypoint_table(self, *args, **kwargs):
        return self.facts._entrypoint_table(*args, **kwargs)

    def _ordered_scenarios(self) -> list[tuple[str, Any]]:
        """scenarios.yaml 에 적은 순서대로 돌려준다.

        호출이 일어나는 차례를 설정이 정한다. 설정에 없는 시나리오가 facts 에 있으면 이름 순으로
        뒤에 붙여서 목차와 페이지 연결에서 빠지지 않게 한다.
        """
        known = [(sid, self.model.scenarios[sid]) for sid in self.scenario_order if sid in self.model.scenarios]
        rest = sorted((sid, sc) for sid, sc in self.model.scenarios.items() if sid not in self.scenario_order)
        return known + rest

    def _visible_messages(self, sc: Any) -> tuple[list[Any], int]:
        """문서에 쓸 메시지와 표시에서 뺀 개수를 돌려준다."""
        hide = (self.scenario_cfg.get(sc.id) or {}).get("hide") or {}
        if not hide:
            return list(sc.messages), 0
        shown = [m for m in sc.messages if not _hidden_message(m, hide)]
        return shown, len(sc.messages) - len(shown)

    def _reading_order(self, scenario_id: str) -> str:
        sc = self.model.scenarios.get(scenario_id)
        if not sc:
            return ""
        # Call-site locations are not callee definitions. Start at the configured
        # entry, then follow the scenario's curated boundaries instead of accessors.
        return (f"1. 진입점 `{sc.entry}`의 입력 검사와 반환 조건을 확인합니다.\n"
                f"2. [{sc.title}](scenarios/{sc.id}.md)에서 주요 호출과 추적 경계를 확인합니다.\n"
                "3. 예약된 호출과 완료 통지를 구분하고, 실행 스레드는 연결 코드와 대조합니다.")


    def _entity_files(self, *args, **kwargs):
        return self.facts._entity_files(*args, **kwargs)

    def _diagram_ref(self, name: str | None) -> str:
        if not name:
            return ""
        mmd = self.cfg.diagrams_dir / f"{name}.mmd"
        if not mmd.exists():
            return ""
        return f"```mermaid\n{mmd.read_text(encoding='utf-8').strip()}\n```"

    # ---- 페이지 뼈대 -------------------------------------------------------------

    def _write_section(self, sec: dict[str, Any], body: str, blocks: list[Block], tables: list[str],
                       verdict: Verdict, omitted: list[str], routes: list[tuple[str, str]] | None = None) -> Path:
        extra = {"section": sec["id"], "generation_method": generation_method(sec, self.cfg.agent.kind)}
        if requires_fingerprint(sec):
            extra["evidence_fingerprint"] = fingerprint(self.model, sec)
            extra["semantic_review"] = "human-review-required"
        status = _status(verdict)
        if sec.get("needs_human"):
            extra["needs_human"] = "true"
            status = "needs-review"
        path = self.cfg.sdd_dir / sec.get("output", f"{sec['id']}.md")
        page = self._render(title=sec["title"], lead=sec.get("lead", ""), body=body,
                            routes=routes or _routes_from_config(sec) or
                                   _routes_from_headings(body),
                            evidence=self._evidence_lines(blocks, tables, verdict, omitted, self._entity_files(sec)),
                            next_link=_next_of(sec), status=status, omitted=omitted, extra=extra, page_path=path)
        if generated_design.enabled(sec):
            from .export_html import _split
            artifact = dict(self.generated_designs[sec['id']][3])
            artifact['body_sha256'] = generated_design.digest(_split(page)[1].strip())
            page = page.replace('\n---\n', '\ngenerated_design: ' + json.dumps(artifact, ensure_ascii=False) + '\n---\n', 1)
            generated_design.verify(self.model, sec, page)
        return self._write(path, page)

    def _render(self, *args, **kwargs):
        return self.writer._render(*args, **kwargs)

    def _rel(self, *args, **kwargs):
        return self.writer._rel(*args, **kwargs)

    def _route_label(self, *args, **kwargs):
        return self.writer._route_label(*args, **kwargs)

    def _evidence_lines(self, *args, **kwargs):
        return self.writer._evidence_lines(*args, **kwargs)

    def _existing_blocks(self, sec: dict[str, Any]) -> dict[str, str]:
        """기존 페이지의 `## 제목` 블록을 제목별로 돌려준다 (절 안의 근거 노트 포함).

        페이지 공통 꼬리(페이지 수준 근거 노트와 다음 단계 줄)는 마지막 절에 섞이지 않게 잘라 낸다."""
        path = self.cfg.sdd_dir / sec.get("output", f"{sec['id']}.md")
        if not path.exists():
            return {}
        text = _FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1)
        text = re.split(r"^\?\?\? note \"근거와 검토 정보\"$", text, maxsplit=1, flags=re.M)[0]
        return {m.group(1).strip(): m.group(0)
                for m in re.finditer(r"^## (.+?)\n.*?(?=^## |\Z)", text, flags=re.S | re.M)}

    def _existing(self, sec: dict[str, Any]) -> str:
        path = self.cfg.sdd_dir / sec.get("output", f"{sec['id']}.md")
        if not path.exists():
            return ""
        text = _FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1)
        text = re.sub(r"^# .*\n", "", text, count=1)
        text = re.sub(r"<!-- sdd:class-diagram -->.*?<!-- /sdd:class-diagram -->", "", text, flags=re.S)
        # 표, 다이어그램, 근거 블록, 번호 목록, 다음 단계 줄은 파이프라인이 다시 만든다. LLM 에는 문단만 돌려준다.
        text = re.sub(r"```mermaid.*?```", "", text, flags=re.S)
        text = re.sub(r"^\?\?\? note.*?(?=^\S|\Z)", "", text, flags=re.S | re.M)
        kept = [l for l in text.splitlines()
                if not l.lstrip().startswith("|") and not l.startswith("다음 단계:")
                and not re.match(r"^\s*\d+\. ", l)]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    def _write(self, path, text):
        return self.writer._write(path, text)


# ---- helpers -----------------------------------------------------------------

def _status(v: Verdict) -> str:
    return "ok" if v.ok else "needs-review"


def _next_of(sec: dict[str, Any]) -> tuple[str, str]:
    nxt = sec.get("next") or {}
    return (str(nxt.get("title", "시스템 개요")), str(nxt.get("link", "overview.md")))


def _routes_from_config(sec: dict[str, Any]) -> list[tuple[str, str]] | None:
    routes = sec.get("routes")
    if not routes:
        return None
    return [(str(r.get("q", "")), str(r.get("to", "#"))) for r in routes]


def _routes_from_headings(body: str) -> list[tuple[str, str]] | None:
    heads = [h for h in re.findall(r"^## (.+)$", body, re.M)
             if h not in ('소스 근거', '클래스 관계', '관련 클래스')][:6]
    if len(heads) < 2:
        return None
    return [(f"{h} 절을 확인합니다.", f"#{slugify(h)}") for h in heads]


def _hidden_message(m: Any, hide: dict[str, Any]) -> bool:
    """이 호출을 표시에서 뺄지 판정한다. 사실에서 지우는 것이 아니라 문서에 쓰지 않는 것이다.

    로깅 매크로와 d-pointer 접근자는 호출 그래프에서 수가 많아서, 걸러내지 않으면 실제 흐름이
    묻힌다. 어떤 이름을 뺄지는 프로젝트마다 다르므로 scenarios.yaml 에서 정한다.
    """
    return hidden_message(m, hide)


def _pkg_selected(name: str, pats: list[str]) -> bool:
    return package_selected(name, pats)


def _match_class(c: ClassInfo, sec: dict[str, Any]) -> bool:
    pats = sec.get("facts", {}).get("classes") or []
    return matches_symbol(c.name, pats)


def _class_table(classes: list[ClassInfo]) -> str:
    rows = ["| 클래스 | 선언 위치 | 상속 | 책임 (주석) |", "|---|---|---|---|"]
    for c in classes:
        bases = ", ".join(f"`{b}`" for b in c.bases) or "–"
        loc = f"`{c.loc.cite()}`" if c.loc else "위치 없음"
        rows.append(f"| `{c.name}` | {loc} | {bases} | {c.brief or '확인 필요'} |")
    return "\n".join(rows)


def _function_table(functions: list[FunctionInfo]) -> str:
    rows = ["| 함수 | 선언 위치 | 정의 위치 | 설명 (주석) |", "|---|---|---|---|"]
    for f in functions:
        decl = f"`{f.loc.cite()}`" if f.loc else "–"
        defn = f"`{f.def_loc.cite()}`" if f.def_loc else "–"
        rows.append(f"| `{f.name}` | {decl} | {defn} | {f.brief or '확인 필요'} |")
    return "\n".join(rows)


def _class_fact(c: ClassInfo) -> str:
    head = f"- {c.kind} {c.name}"
    if c.loc:
        head += f" `{c.loc.cite()}`"
    if c.bases:
        head += " : " + ", ".join(c.bases)
    if c.brief:
        head += f" -- {c.brief}"
    lines = [head]
    for m in c.methods[:12]:
        line = f"  - {m.name}()"
        # 정의 위치(.cpp)가 있으면 그쪽을 인용한다. 개발자가 열어 볼 곳이 거기다.
        for l in (m.def_loc, m.loc):
            if l:
                line += f" `{l.cite()}`"
                break
        if m.brief:
            line += f" -- {m.brief}"
        lines.append(line)
    if len(c.methods) > 12:
        lines.append(f"  - (메서드 {len(c.methods) - 12} 개 생략)")
    return "\n".join(lines)


def _subsection(existing: str, heading: str) -> str:
    """기존 문서에서 `## heading` 아래 본문만 돌려준다."""
    if not existing:
        return ""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |^\?\?\? |\Z)", existing, re.S | re.M)
    return m.group(1).strip() if m else ""
