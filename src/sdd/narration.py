"""Budget, call and validate model prose through a minimal chat port."""
from __future__ import annotations
from typing import Any, Protocol
from .budget import Block, fit
from .validate import Verdict, check, extract_citations, normalize_citations, strip_echo, strip_headings
from .manuscript import describe, lint, unwrap
from .semantic import known_names, normalize_symbols, review as semantic_review
from .prompting import compose_system_prompt

class ChatPort(Protocol):
    def chat(self, system: str, user: str, tag: str = "prompt", response_schema: dict | None = None) -> str: ...

class Narrator:
    def __init__(self, cfg, model, agent: ChatPort, record):
        self.cfg, self.model, self.agent = cfg, model, agent
        self._record_review = record
        self.system = compose_system_prompt(cfg)
        self.section_tpl = (cfg.prompts_dir / "section.md").read_text(encoding="utf-8")
        self.allowed = model.citations()
        self.symbols = {n for n in known_names(model) if n}
        self.symbols |= {n.rsplit("::", 1)[-1] for n in set(self.symbols) if "::" in n}

    def ask(self, tag: str, sec: dict[str, Any], title: str, blocks: list[Block],
             existing: str) -> tuple[str, list[str], Verdict]:
        # Prior prose is not evidence. In particular, an A-side absence claim
        # must not contaminate B after a class is added.
        if sec.get("semantic_review"):
            existing = ""
        if existing:
            blocks = blocks + [Block("existing", existing, 9)]
        reserved = len(self.system) + len(self.section_tpl) + len(title) + 400
        facts, omitted = fit(blocks, self.cfg.agent.max_input_chars, reserved=reserved)
        existing_txt = existing if existing and "existing" not in omitted else "(없음)"
        answers = "\n".join(f"- {a}" for a in (sec.get("answers") or ["이 절의 독자가 알아야 하는 구조와 관계는 무엇인가?"]))
        fields = {"title": title, "reader": sec.get("reader", "이 HAL 을 수정하는 개발자"),
                  "answers": answers, "facts": facts}
        user = self.section_tpl.format(**fields, existing=existing_txt)
        # 메아리 판정에서 기존 본문은 뺀다. 프롬프트가 "구조를 유지하고 바뀐 부분만 고치라" 고
        # 지시하므로 모델이 기존 문장을 그대로 다시 쓰는 것이 정상이다. 그 문장까지 메아리로
        # 지우면 증분 생성에서 본문이 통째로 사라지고 빈 페이지가 남는다.
        echo_source = self.system + "\n" + self.section_tpl.format(**fields, existing="(없음)")
        if existing:
            # 기존 본문은 사실 블록으로도 들어가므로 렌더링된 프롬프트에서 한 번 더 뺀다.
            echo_source = echo_source.replace(existing, "")
        # 페이지 머리말(lead)은 뼈대가 굵게 한 번 찍는다. 모델이 그 문장을 본문 첫 줄로 다시 쓰면
        # 같은 문장이 두 번 보이므로 메아리로 본다.
        if sec.get("lead"):
            echo_source += "\n" + str(sec["lead"])
        if self.cfg.agent.kind == "dry-run":
            # 프롬프트만 기록한다. 검증할 출력이 없으므로 사람이 볼 문서로 표시한다.
            text = self.agent.chat(self.system, user, tag=tag)
            verdict = Verdict(ok=False, notes=["dry-run: LLM 을 호출하지 않았습니다."])
            self._record_review(tag, text, verdict, omitted)
            return text, omitted, verdict

        verdict = Verdict(ok=False)
        text = ""
        for attempt in range(self.cfg.max_retries + 1):
            raw = self.agent.chat(self.system, user, tag=f"{tag}_{attempt}")
            text = normalize_symbols(normalize_citations(unwrap(raw), self.allowed), self.model)
            text = strip_headings(strip_echo(text, echo_source))
            verdict = check(text, self.allowed, require=self.cfg.require_citations)
            cite_failed = not verdict.ok
            # 인용과 별개로 문장 형태 위반(종결어미, 대화체, 프롬프트 누설)도 반려 사유다.
            problems = lint(text, self.symbols)
            if problems:
                verdict.ok = False
                verdict.notes.extend(describe(problems))
            if sec.get("semantic_review"):
                findings = semantic_review(text, self.model, set(extract_citations(facts)))
                if omitted:
                    findings.append("설명 입력에서 근거 블록이 생략됐습니다: " + ", ".join(omitted))
                if findings:
                    verdict.ok = False
                    verdict.notes.extend(findings)
            if verdict.ok:
                break
            retry_note = ("\n\n## 이전 출력의 문제\n" + "\n".join(f"- {n}" for n in verdict.notes)
                          + "\n위 문제를 고쳐서 다시 씁니다.")
            user += retry_note
            echo_source += retry_note
            if cite_failed:
                # 인용 검증 실패에만 인용 복사 지시를 붙인다. 린트만 실패했을 때는 문장 교정에 집중시킨다.
                usable = list(dict.fromkeys(extract_citations(facts)))[:12]
                cite_note = (" 사실 블록에 적힌 `파일:줄` 을 디렉터리까지 그대로 복사해서 인용합니다."
                             + ("\n인용할 수 있는 위치 예: " + ", ".join(f"`{c}`" for c in usable) if usable else ""))
                user += cite_note
                echo_source += cite_note
        self._record_review(tag, text, verdict, omitted)
        return text, omitted, verdict
