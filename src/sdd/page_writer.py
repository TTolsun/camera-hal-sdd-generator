"""Markdown page layout, metadata and persistence, separate from prose generation."""
from __future__ import annotations
import datetime as dt
import os
import re
from pathlib import Path
from .budget import Block
from .document_metadata import generation_info
from .markdown_text import slugify
from .validate import Verdict, extract_citations

class PageWriter:
    def __init__(self, cfg, model, page_titles):
        self.cfg, self.model, self.page_titles = cfg, model, page_titles
        self.page_tpl = (cfg.templates_dir / "page.md").read_text(encoding="utf-8")

    def _render(self, title: str, lead: str, body: str, routes: list[tuple[str, str]] | None, evidence: str,
                next_link: tuple[str, str], status: str, omitted: list[str], extra: dict[str, str],
                page_path: Path) -> str:
        meta = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source_commit": self.model.meta.get("source_commit", ""),
            "status": status,
            **extra,
        }
        method = extra.get("generation_method", "")
        if method in ("facts-and-llm", "mixed"):
            meta["agent"] = f"{self.cfg.agent.kind}/{self.cfg.agent.model}"
        label, scope = generation_info(method)
        evidence = f"    - 생성 방식: {label}\n    - 검증 범위: {scope}\n" + evidence
        fm = "\n".join(f"{k}: {v}" for k, v in meta.items())
        if omitted:
            fm += "\nfacts_omitted:\n" + "\n".join(f"  - {o}" for o in omitted)
        routes_md = ""
        if routes:
            headings = {slugify(h): h for h in re.findall(r"^## (.+)$", body, re.M)}
            routes_md = "| 지금 확인할 내용 | 이동할 절 |\n|---|---|\n" + "\n".join(
                f"| {q} | [{self._route_label(to, headings)}]({self._rel(to, page_path)}) |" for q, to in routes)
        return self.page_tpl.format(frontmatter=fm, title=title, lead=lead or "이 절의 표부터 확인하세요.",
                                    routes=routes_md, body=body.strip(), evidence=evidence,
                                    next_title=next_link[0], next_link=self._rel(next_link[1], page_path))

    def _rel(self, link: str, page_path: Path) -> str:
        """설정과 코드의 링크는 sdd 루트 기준이다. 페이지가 하위 디렉터리에 있으면 그 페이지 기준으로 바꾼다."""
        if link.startswith("#") or "://" in link:
            return link
        target, _, anchor = link.partition("#")
        rel = os.path.relpath(self.cfg.sdd_dir / target, page_path.parent).replace("\\", "/")
        return rel + (f"#{anchor}" if anchor else "")

    def _route_label(self, to: str, headings: dict[str, str]) -> str:
        if to.startswith("#"):
            return headings.get(to[1:], to[1:].replace("-", " "))
        name = to.split("#", 1)[0]
        return self.page_titles.get(name) or self.page_titles.get(Path(name).name) or Path(name).stem

    def _evidence_lines(self, blocks: list[Block], tables: list[str], verdict: Verdict, omitted: list[str],
                        extra_files: set[str] | None = None) -> str:
        text = "\n".join([b.text for b in blocks] + tables)
        files = sorted({c.rsplit(":", 1)[0] for c in extract_citations(text)} | (extra_files or set()))
        meta = self.model.meta
        lines = [
            "- 근거 파일: " + (", ".join(f"`{f}`" for f in files) if files else "(없음)"),
            f"- 근거 수준: 코드 확인 (정적 분석, {meta.get('build_config', 'ndk-build')} 구성, commit `{meta.get('source_commit', '')[:10] or '?'}`)",
            "- 자동 검사 (인용·문장 및 설정된 구조 검사): " + ("통과" if verdict.ok else "실패 (" + "; ".join(verdict.notes) + ")"),
        ]
        if omitted:
            lines.append("- 입력 예산 때문에 제외된 사실: " + ", ".join(omitted))
        lines.append(f"- 검토 상태 기록일: {dt.date.today().isoformat()} · 사람 검토 전")
        return "\n".join("    " + l for l in lines)

    @staticmethod
    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 플랫폼과 무관하게 LF 로 쓴다. Windows 개발자와 Linux CI 가 같은 파일을 만들어야 diff 가 조용하다.
        path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
        return path
