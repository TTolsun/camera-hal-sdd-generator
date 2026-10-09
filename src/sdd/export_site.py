"""Reading-oriented, multi-page SDD site. Presentation never changes review verdicts."""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import markdown

from .config import Config, section_output
from .diagrams import section_diagram, diagram_block
from .document_metadata import generation_info
from .export_html import _mermaid_fence, _nav_entries, _split, _title_of_text
from .facts.model import KnowledgeModel

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"
MERMAID_ENTRY = "mermaid.esm.min.mjs"
ASSETS = Path(__file__).parent / "site_assets"

# 소스 열람 호스트별 인용 링크 형식. 커밋 확인(40자리 hex)과 경로 검증은 형식과 무관하게 적용된다.
SOURCE_LINK_TEMPLATES = {
    "github": "{url}/blob/{commit}/{file}#L{line}",
    "gitiles": "{url}/+/{commit}/{file}#{line}",
}


def source_link_template(settings: dict) -> str:
    """site 설정에서 인용 링크 템플릿을 정한다.

    `site.source_link_template` 이 있으면 그대로 쓰고, 없으면 `site.source_link` 가 가리키는
    호스트 형식(github 기본, gitiles)을 쓴다. 자리표시자가 어긋난 템플릿은 게시 시점에 조용히
    깨진 링크를 만들므로 여기서 즉시 실패시킨다.
    """
    template = str(settings.get("source_link_template") or "")
    if not template:
        host = str(settings.get("source_link", "github"))
        template = SOURCE_LINK_TEMPLATES.get(host, "")
        if not template:
            raise RuntimeError(f"site.source_link 값을 모릅니다: {host} "
                               f"(지원: {', '.join(sorted(SOURCE_LINK_TEMPLATES))}. "
                               "다른 호스트는 site.source_link_template 로 형식을 지정하세요)")
    try:
        template.format(url="u", commit="c", file="f", line=1)
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError("site.source_link_template 의 자리표시자는 {url} {commit} {file} {line} "
                           f"만 쓸 수 있습니다: {e}")
    return template


def _path(rel: str) -> str:
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or ":" in str(p) or p.suffix != ".md":
        raise RuntimeError(f"Invalid documentation path: {rel}")
    return str(p)


def _href(rel: str, current: str) -> str:
    return quote(posixpath.relpath(rel, posixpath.dirname(current) or "."), safe="/.-")


def _html_path(rel: str) -> str:
    return str(PurePosixPath(rel).with_suffix(".html"))



def _approval_label(state: str, entry: dict | None) -> str:
    if state == "approved" and entry:
        return f"사람 검토 승인 · {entry.get('approved_by', '')} {str(entry.get('approved_at', ''))[:10]}".rstrip()
    if state == "stale":
        return "승인 이후 본문 변경 · 재검토 필요"
    return "사람 검토 전"


def _status(meta: dict, approval: str = "unreviewed", approval_entry: dict | None = None) -> str:
    status = str(meta.get("status", "unrecorded"))
    check_name = "자동 검사" if meta.get("semantic_review") or meta.get("generation_method") else "인용 검사"
    label = {"ok": f"{check_name} 통과", "needs-review": f"{check_name} 확인 필요"}.get(status, f"{check_name} 미기록")
    return (f'<span class="review-state">{html.escape(_approval_label(approval, approval_entry))}</span>'
            f'<span>{label} · <code>{html.escape(status)}</code></span>')


def _render(body: str, rel: str, known: set[str], model: KnowledgeModel | None,
            source_url: str, commit: str, link_template: str = SOURCE_LINK_TEMPLATES["github"]) -> tuple[str, str, list[dict]]:
    def slug(value: str, separator: str) -> str:
        return re.sub(r"[-\s]+", separator, re.sub(r"[^\w\s-]", "", value.lower().strip()))

    md = markdown.Markdown(extensions=["tables", "toc", "attr_list", "pymdownx.details", "pymdownx.superfences"],
                           extension_configs={"toc": {"slugify": slug}, "pymdownx.superfences": {"custom_fences": [
                               {"name": "mermaid", "class": "mermaid", "format": _mermaid_fence}]}})
    rendered = md.convert(body)

    def link(match: re.Match) -> str:
        href = html.unescape(match[1])
        parts = urlsplit(href)
        if parts.scheme or parts.netloc or not parts.path:
            return match[0]
        target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), parts.path))
        if target in known:
            dest = _href(_html_path(target), _html_path(rel))
            if parts.fragment:
                dest += "#" + quote(parts.fragment)
            return f'href="{html.escape(dest, quote=True)}"'
        return match[0]

    rendered = re.sub(r'href="([^"]+)"', link, rendered)
    if model and source_url and re.fullmatch(r"[0-9a-f]{40}", commit):
        valid = model.citations() if commit == model.meta.get("source_commit") else set()

        def citation(match: re.Match) -> str:
            cite = html.unescape(match[1])
            if cite not in valid:
                return match[0]
            file, line = cite.rsplit(":", 1)
            if PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts:
                return match[0]
            url = link_template.format(url=source_url.rstrip("/"), commit=commit,
                                       file=quote(file, safe="/"), line=line)
            return f'<a class="citation" href="{html.escape(url, quote=True)}">{match[0]}</a>'

        rendered = re.sub(r"<code>([^<>]+:\d+)</code>", citation, rendered)
    rendered = re.sub(r"(<table>.*?</table>)", r'<div class="table-scroll" tabindex="0" role="region" aria-label="표">\1</div>', rendered, flags=re.S)
    return rendered, md.toc, md.toc_tokens


def _place_scenarios(entries: list[tuple[str, str, str]], order: list[str]) -> list[tuple[str, str, str]]:
    """시나리오 하위 페이지를 목차 바로 뒤에, 설정한 호출 차례대로 놓는다.

    파일 이름 순으로 두면 메뉴가 호출이 일어나는 차례와 어긋나고, 목차 페이지와 떨어져 붙는다.
    설정에 없는 시나리오는 이름 순으로 뒤에 놓아 메뉴에서 빠지지 않게 한다.
    """
    subs = [e for e in entries if e[2].startswith("scenarios/") and e[2] != "scenarios/index.md"]
    if not subs:
        return entries
    rank = {f"scenarios/{sid}.md": i for i, sid in enumerate(order)}
    subs.sort(key=lambda e: (rank.get(e[2], len(rank)), e[2]))
    rest = [e for e in entries if e not in subs]
    index_at = next((i for i, e in enumerate(rest) if e[2] == "scenarios/index.md"), None)
    if index_at is None:
        return rest + subs
    return rest[:index_at + 1] + subs + rest[index_at + 1:]


def _is_child(rel: str) -> bool:
    """목차 페이지에 딸린 하위 문서인지 판정한다."""
    return "/" in rel and not rel.endswith("/index.md")


def _branch_of(rel: str) -> str:
    """하위 문서를 묶는 가지 이름. 목차 페이지와 그 하위 문서가 같은 값을 가진다."""
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def _grouped(entries: list[tuple[str, str, str]], preferred: list[str] | None = None) -> list[tuple[str, str, str]]:
    """그룹 단위로 묶는다. `site.nav_groups` 에 적은 그룹이 그 순서대로 앞에 온다.

    같은 그룹의 항목이 목록에서 떨어져 있으면 그룹 제목이 두 번 나온다. 그룹 안의 순서는 섹션
    순서를 그대로 두고 그룹 단위로만 모아서, 문서를 읽는 차례와 메뉴의 분류를 따로 정할 수 있게 한다.
    설정에 없는 그룹은 처음 나온 순서대로 뒤에 붙인다.
    """
    present = {group for group, _, _ in entries}
    order: list[str] = [g for g in (preferred or []) if g in present]
    for group, _, _ in entries:
        if group not in order:
            order.append(group)
    return [e for group in order for e in entries if e[0] == group]


def export_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None) -> Path:
    from .document_health import enforce
    enforce(cfg)
    from .site_build import build_site
    return build_site(cfg, out or cfg.build_dir / "site", _render_site, mermaid_src)


def _render_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None) -> Path:
    from .document_health import retired_paths
    retired = retired_paths(cfg)
    settings = cfg.raw.get("site", {}) or {}
    title = str(settings.get("title", "Camera HAL SDD"))
    source_url = str(settings.get("source_url", ""))
    link_template = source_link_template(settings)
    # Mermaid 우선순위: --mermaid > site.mermaid > site.mermaid_dir(사이트에 동봉) > 공개 CDN.
    mermaid_dir = settings.get("mermaid_dir")
    mermaid_src = mermaid_src or str(settings.get("mermaid") or "")
    if not mermaid_src:
        mermaid_src = f"assets/mermaid/{MERMAID_ENTRY}" if mermaid_dir else MERMAID
    out = (out or cfg.build_dir / "site").resolve()
    if out == cfg.sdd_dir.resolve() or out in cfg.sdd_dir.resolve().parents:
        raise RuntimeError("Site output must be separate from the Markdown source directory")
    sections = {_path(section_output(s)): s for s in cfg.sections()}
    missing = [rel for rel, section in sections.items()
               if section.get("kind") != "manual" and not (cfg.sdd_dir / rel).is_file()]
    if missing:
        raise RuntimeError("Configured pages are missing; run generate first: " + ", ".join(missing))
    # 그룹은 sections.yaml 의 group 이 정한다. 없으면 한 그룹으로 묶는다.
    default_group = str(settings.get("nav_group") or "설계 문서")
    scenario_group = next((str(s.get("group") or default_group) for s in sections.values()
                           if s.get("kind") == "per-scenario"), default_group)
    entries = [(str(s.get("group") or default_group), s.get("title", rel), rel) for rel, s in sections.items()
               if (cfg.sdd_dir / rel).is_file()]
    # Include configured MkDocs pages and scenario pages without losing section ordering.
    for group, name, rel in _nav_entries(cfg.root / "mkdocs.yml", cfg.sdd_dir):
        if rel in retired:
            continue
        if sections and not (cfg.root / "mkdocs.yml").exists():
            # Old Markdown can remain for history; removed sections must not return to the menu.
            if not (rel.startswith("scenarios/") and any(s.get("kind") == "per-scenario" for s in sections.values())):
                continue
        rel = _path(rel)
        if (cfg.sdd_dir / rel).is_file() and rel not in {e[2] for e in entries}:
            inherited = scenario_group if rel.startswith("scenarios/") else default_group
            entries.append((group or inherited, name, rel))
    if not entries:
        raise RuntimeError("No generated Markdown pages found")
    entries = _grouped(entries, [str(g) for g in (settings.get("nav_groups") or [])])
    entries = _place_scenarios(entries, [sc["id"] for sc in cfg.scenarios()])
    texts = {rel: (cfg.sdd_dir / rel).read_text(encoding="utf-8") for _, _, rel in entries}
    # 사람 승인 장부. 표시가 검사 결과를 바꾸지는 않지만, 승인·미승인 상태를 구분해 보여 준다.
    from . import approvals as approvals_mod
    ledger = approvals_mod.load(cfg)
    approval_states = {rel: approvals_mod.page_status(ledger, rel, texts[rel]) for rel in texts}
    if settings.get("require_approval", False):
        blocked = sorted(rel for rel, state in approval_states.items() if state != "approved")
        if blocked:
            raise RuntimeError("site.require_approval: 사람 검토 승인이 없는 문서가 있어 게시를 중단합니다: "
                               + ", ".join(blocked) + " (`sdd accept <문서>` 로 승인 기록)")
    if "index.md" not in texts:
        intro = settings.get("intro")
        if intro:
            texts["index.md"] = (cfg.root / str(intro)).read_text(encoding="utf-8")
        else:
            texts["index.md"] = "# 문서 안내\n\n코드에서 추출한 구조와 문장별 근거를 함께 확인하세요.\n"
        texts["index.md"] += "\n## 문서 목록\n\n| 문서 | 자동 검사 | 검토 상태 |\n|---|---|---|\n"
        for _, name, rel in entries:
            status = _split(texts[rel])[0].get("status", "unrecorded")
            label = _approval_label(approval_states.get(rel, "unreviewed"), ledger["pages"].get(rel))
            texts["index.md"] += f"| [{name}]({rel}) | `{status}` | {label} |\n"
        entries.insert(0, ("시작하기", "문서 안내", "index.md"))
        approval_states["index.md"] = "unreviewed"
    model = KnowledgeModel.load(cfg.facts_path) if cfg.facts_path.exists() else None
    if model is None and any(s.get("kind", "prose") == "prose" and s.get("facts", {}).get("classes")
                            and {**(cfg.raw.get("diagrams") or {}), **(s.get("diagram") or {})}.get("enabled", False)
                            for s in sections.values()):
        raise RuntimeError("facts.json is required to generate configured class diagrams")
    known = set(texts)
    rendered_pages = {}
    search = []
    diagram_sources = {}
    for group, name, rel in entries:
        meta, body = _split(texts[rel])
        if meta.get("generation_method") and meta.get("generation_method") != "manual":
            if model is None or meta.get("source_commit") != model.meta.get("source_commit"):
                raise RuntimeError(f"Facts and page source commits differ: {rel}")
        if meta.get("scenario_fingerprint"):
            from .scenario_document import build as scenario_document, fingerprint as scenario_fingerprint
            sid = str(meta.get("scenario_id", ""))
            settings = next((s for s in cfg.scenarios() if s["id"] == sid), {})
            sc = model.scenarios.get(sid) if model else None
            if sc is None or meta["scenario_fingerprint"] != scenario_fingerprint(sc, settings):
                raise RuntimeError(f"Scenario evidence changed; regenerate page before publishing: {rel}")
            sc_section = next((s for s in cfg.sections() if s["id"] == meta.get("section")), {})
            policy = {**(cfg.raw.get("diagrams") or {}), **(sc_section.get("diagram") or {})}
            scenario_document(sc, settings, int(policy.get("max_nodes", 16)))
            sources = re.findall(r"```mermaid\n(.*?)\n```", body, re.S)
            if len(sources) == 1:
                diagram_sources[rel] = sources[0]
        page_title = _title_of_text(body)
        body = re.sub(r"^\s*# .+\n", "", body, count=1)
        section = sections.get(rel, {})
        if section and section.get("kind") != "manual":
            if section.get("design_requirements"):
                from .design_contracts import enforce
                if model is None:
                    raise RuntimeError("facts.json is required to verify design requirements")
                enforce(model, section)
            from .evidence import fingerprint, requires_fingerprint
            if requires_fingerprint(section) or meta.get("evidence_fingerprint"):
                if model is None or meta.get("evidence_fingerprint") != fingerprint(model, section):
                    raise RuntimeError(f"Design evidence changed; regenerate page before publishing: {rel}")
        if section and section.get("kind", "prose") == "prose":
            if model and meta.get("source_commit") != model.meta.get("source_commit"):
                raise RuntimeError(f"Facts and page source commits differ: {rel}")
            diagram = section_diagram(cfg, model, section) if model else ""
            block = diagram_block(diagram)
            if "<!-- sdd:class-diagram -->" in body:
                # Keep the heading for existing route links, but never retain stale edges.
                replacement = block.strip() or "## 클래스 관계\n\n현재 설정에서 표시할 클래스 관계 그림이 없습니다."
                body = re.sub(r"<!-- sdd:class-diagram -->.*?<!-- /sdd:class-diagram -->", lambda _: replacement, body, flags=re.S)
                block = ""
            if diagram:
                diagram_sources[rel] = diagram
                before, marker, after = body.partition('??? note "근거와 검토 정보"')
                # Move intact generated sections into reading order; preserve their wording.
                parts = re.fullmatch(r"(.*?)^(## 관련 클래스\n.*?)(^## 구조 설명\n.*)", before, re.S | re.M)
                if parts:
                    body = parts[1] + parts[3] + block + parts[2] + marker + after
                else:
                    body = before + block + marker + after
        content, toc, tokens = _render(body, rel, known, model, source_url, str(meta.get("source_commit", "")),
                                       link_template)
        rendered_pages[rel] = (page_title, meta, content, toc)
        search.append({"title": page_title, "page": page_title, "url": _html_path(rel)})

        def headings(items: list[dict]) -> None:
            for item in items:
                search.append({"title": html.unescape(re.sub("<[^>]+>", "", item["name"])),
                               "page": page_title, "url": _html_path(rel) + "#" + quote(item["id"])})
                headings(item.get("children", []))

        headings(tokens)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSETS, out / "assets", dirs_exist_ok=True)
    if mermaid_dir:
        # Mermaid ESM 은 본체 옆 chunks/ 를 상대 경로로 불러오므로 디렉터리째 사이트에 담는다.
        # 그래야 CDN 없는 사내망·오프라인 열람에서도 그림이 뜬다. `sdd fetch-mermaid` 가 이 구조를 만든다.
        src_dir = (cfg.root / str(mermaid_dir)).resolve()
        if not (src_dir / MERMAID_ENTRY).is_file():
            raise RuntimeError(f"site.mermaid_dir 에 {MERMAID_ENTRY} 가 없습니다: {src_dir} "
                               "(`sdd fetch-mermaid` 로 준비하세요)")
        shutil.copytree(src_dir, out / "assets" / "mermaid", dirs_exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    for index, (group, name, rel) in enumerate(entries):
        current = _html_path(rel)
        root = _href("index.html", current).removesuffix("index.html") or "./"
        page_title, meta, content, toc = rendered_pages[rel]
        nav = []
        last_group = None
        branch_open = False
        for nav_group, nav_title, nav_rel in entries:
            child = _is_child(nav_rel)
            if not child and branch_open:
                nav.append("</details>")
                branch_open = False
            if nav_group != last_group:
                if nav_group:
                    nav.append(f'<p class="nav-group">{html.escape(nav_group)}</p>')
                last_group = nav_group
            active = ' aria-current="page"' if nav_rel == rel else ""
            link = (f'<a{" class=" + chr(34) + "nav-sub" + chr(34) if child else ""}'
                    f' href="{_href(_html_path(nav_rel), current)}"{active}>{html.escape(nav_title)}</a>')
            if child and not branch_open:
                # 하위 문서는 접었다 펼 수 있게 묶는다. 읽고 있는 가지만 펴 둔다.
                count = sum(1 for _, _, r in entries if _branch_of(r) == _branch_of(nav_rel) and _is_child(r))
                opened = " open" if _branch_of(rel) == _branch_of(nav_rel) else ""
                nav.append(f'<details class="nav-branch"{opened}>'
                           f'<summary>하위 문서 {count} 편</summary>')
                branch_open = True
            nav.append(link)
        if branch_open:
            nav.append("</details>")
        previous_next = []
        for offset, label in [(-1, "이전"), (1, "다음")]:
            other = index + offset
            if 0 <= other < len(entries):
                _, dest_title, dest_rel = entries[other]
                previous_next.append(f'<a class="{"previous" if offset < 0 else "next"}" href="{_href(_html_path(dest_rel), current)}"><small>{label}</small>{html.escape(dest_title)} {"←" if offset < 0 else "→"}</a>')
        info = []
        method_label, method_scope = generation_info(str(meta.get("generation_method", "")))
        if meta:
            info.append(f'<dt>생성 방식</dt><dd>{html.escape(method_label)}</dd>')
            info.append(f'<dt>검증 범위</dt><dd>{html.escape(method_scope)}</dd>')
        for key, label in [("source_commit", "분석 기준 커밋"), ("generated_at", "문서 생성 시각"), ("agent", "문장 생성 모델")]:
            if meta.get(key):
                info.append(f'<dt>{label}</dt><dd><code>{html.escape(str(meta[key]))}</code></dd>')
        downloads = ""
        if rel in sections or (cfg.sdd_dir / rel).is_file():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cfg.sdd_dir / rel, out / rel)
            downloads = f'<a href="{_href(rel, current)}">Markdown 원문 ↗</a>'
        if rel in diagram_sources:
            mmd = str(PurePosixPath(rel).with_suffix(".mmd"))
            (out / mmd).write_text(diagram_sources[rel] + "\n", encoding="utf-8", newline="\n")
            downloads += f' <a href="{_href(mmd, current)}">Mermaid 원문 ↗</a>'
        evidence = f'<section class="evidence"><h2 id="page-evidence">생성 근거</h2><dl>{"".join(info)}</dl>{downloads}</section>' if info else ""
        status = (_status(meta, approval_states.get(rel, "unreviewed"), ledger["pages"].get(rel))
                  if meta else '<span class="review-state">검토용 문서</span>')
        if meta:
            status += f'<span class="generation-method">{html.escape(method_label)}</span>'
        config_json = json.dumps({"root": root, "mermaid": mermaid_src}, ensure_ascii=False).replace("<", "\\u003c")
        doc = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title)} · {html.escape(title)}</title><link rel="stylesheet" href="{root}assets/reading.css"></head>
<body><a class="skip" href="#main">본문으로 이동</a>
<header class="site-header"><a class="brand" href="{root}index.html"><span class="brand-mark" aria-hidden="true">◉</span>{html.escape(title)}</a>
<div class="header-actions"><button id="search-open" hidden>문서 찾기 <kbd>Ctrl K</kbd></button><button id="menu-toggle" aria-controls="sidebar" aria-expanded="false" hidden>메뉴</button></div></header>
<div class="layout"><aside id="sidebar"><p class="edition">DESIGN DOCUMENTATION</p><nav aria-label="문서 메뉴">{''.join(nav)}</nav><p class="sidebar-note">코드에서 구조를 추출하고<br>근거와 함께 검토합니다.</p></aside>
<main id="main"><p class="breadcrumb">{html.escape(group)} <span>/</span> {html.escape(page_title)}</p><h1>{html.escape(page_title)}</h1><div class="page-state">{status}</div>
<details class="mobile-toc"><summary>이 페이지의 목차</summary>{toc}</details><article>{content}</article>{evidence}<nav class="pagination" aria-label="이전과 다음 문서">{''.join(previous_next)}</nav>
<footer>Generated by camera-hal-sdd-generator · 인용 검사와 사람의 내용 검토는 별도입니다.</footer></main>
<aside class="page-toc"><nav aria-label="현재 페이지 목차"><p>이 페이지에서</p>{toc}</nav></aside></div>
<dialog id="search-dialog" aria-labelledby="search-title"><div class="dialog-head"><h2 id="search-title">문서 찾기</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><label for="search-input">문서 제목과 절 제목 검색</label><input id="search-input" type="search" autocomplete="off" placeholder="예: Pipeline, 클래스 관계"><p id="search-count" role="status"></p><ul id="search-results"></ul></dialog>
<dialog id="diagram-dialog" aria-labelledby="diagram-title"><div class="dialog-head"><h2 id="diagram-title">클래스 관계</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><div class="diagram-tools"><label for="node-search">요소 찾기</label><input id="node-search" type="search" placeholder="클래스 이름"><output id="node-count" aria-live="polite"></output><button id="zoom-out" aria-label="축소">−</button><output id="zoom-value">100%</output><button id="zoom-in" aria-label="확대">+</button><button id="zoom-fit">화면에 맞춤</button><button id="zoom-reset">100%</button></div><div id="diagram-viewport" tabindex="0" role="region" aria-label="확대된 다이어그램"><div id="diagram-canvas"></div></div></dialog>
<script id="site-config" type="application/json">{config_json}</script><script defer src="{root}assets/site.js"></script></body></html>'''
        target = out / current
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8", newline="\n")
    (out / "assets" / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    from .site_localization import localize_site
    localize_site(cfg, out)
    return out
