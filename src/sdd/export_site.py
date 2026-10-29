"""Reading-oriented, multi-page SDD site. Presentation never changes review verdicts."""

from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit


from . import glossary
from .config import Config, SiteConfig, section_output
from .diagrams import section_diagram, diagram_block
from .document_metadata import generation_info, reader_label, split_frontmatter
from .export_html import _nav_entries, _title_of_text
from .site_markdown import SOURCE_LINK_TEMPLATES, _href, _html_path, _render
from .facts.model import KnowledgeModel

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"
MERMAID_ENTRY = "mermaid.esm.min.mjs"
ASSETS = Path(__file__).parent / "site_assets"

# 소스 열람 호스트별 인용 링크 형식. 커밋 확인(40자리 hex)과 경로 검증은 형식과 무관하게 적용된다.



def source_link_template(settings: SiteConfig | dict) -> str:
    """site 설정에서 인용 링크 템플릿을 정한다.

    `site.source_link_template` 이 있으면 그대로 쓰고, 없으면 `site.source_link` 가 가리키는
    호스트 형식(github 기본, gitiles)을 쓴다. 자리표시자가 어긋난 템플릿은 게시 시점에 조용히
    깨진 링크를 만들므로 여기서 즉시 실패시킨다.
    """
    if isinstance(settings, dict):
        settings = SiteConfig.from_mapping(settings)
    template = str(settings.source_link_template or "")
    if not template:
        host = str(settings.source_link)
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


def _approval_label(state: str, entry: dict | None) -> str:
    if state == "approved" and entry:
        return f"사람 검토 승인 · {entry.get('approved_by', '')} {str(entry.get('approved_at', ''))[:10]}".rstrip()
    if state == "stale":
        return "승인 이후 본문 변경 · 재검토 필요"
    return "사람 검토 전"


def _check(meta: dict) -> tuple[str, str, str]:
    """자동 검사의 이름, 결과, 확인 범위. 상단에는 쉬운 말만 쓰고 상태 코드는 생성 근거에 둔다."""
    status = str(meta.get("status", "unrecorded"))
    if meta.get("semantic_review") or meta.get("generation_method"):
        # 검사 항목은 생성 방식마다 다르므로 바로 위의 검증 범위에 맡기고 여기서는 반복하지 않는다.
        name, scope = "자동 검사", "검사한 항목은 검증 범위에 적혀 있습니다."
    else:
        name, scope = "인용 검사", "인용한 코드 위치가 분석 결과에 있는지만 확인했습니다."
    result = {"ok": "통과", "needs-review": "확인 필요"}.get(status, "미기록")
    return name, result, scope + " 설명 내용이 맞는지는 사람이 확인합니다."


def _status(meta: dict, approval: str = "unreviewed", approval_entry: dict | None = None) -> str:
    name, result, _ = _check(meta)
    return (f'<span class="review-state">{html.escape(_approval_label(approval, approval_entry))}</span>'
            f'<span>{name} {result}</span>')



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


def _nav_section(rel: str, sections: dict[str, dict]) -> str:
    """Scenario children inherit the task category of their configured index."""
    section = sections.get(rel, sections.get(f"{_branch_of(rel)}/index.md", {}))
    return str(section.get("nav_section") or "")


def _sectioned(entries: list[tuple[str, str, str]], sections: dict[str, dict]) -> list[tuple[str, str, str]]:
    # Keep the first appearance of each task within its reader group. No task
    # names or project-specific categories belong in the common renderer.
    buckets: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for entry in entries:
        buckets.setdefault((entry[0], _nav_section(entry[2], sections)), []).append(entry)
    return [entry for bucket in buckets.values() for entry in bucket]


def export_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None) -> Path:
    from .document_health import enforce
    enforce(cfg)
    from .site_build import build_site
    return build_site(cfg, out or cfg.build_dir / "site", _render_site, mermaid_src)


def _site_navigation(cfg, settings, retired):
    sections = {_path(section_output(s)): s for s in cfg.sections()}
    missing = [rel for rel, section in sections.items()
               if section.get("kind") != "manual" and not (cfg.sdd_dir / rel).is_file()]
    if missing:
        raise RuntimeError("Configured pages are missing; run generate first: " + ", ".join(missing))
    # 그룹은 sections.yaml 의 group 이 정한다. 없으면 한 그룹으로 묶는다.
    default_group = str(settings.nav_group or "설계 문서")
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
    entries = _grouped(entries, [str(g) for g in (settings.nav_groups or [])])
    entries = _sectioned(entries, sections)
    entries = _place_scenarios(entries, [sc["id"] for sc in cfg.scenarios()])
    return sections, entries


def _prepare_site_pages(cfg, settings, sections, entries, *, check_consistency=True):
    texts = {rel: (cfg.sdd_dir / rel).read_text(encoding="utf-8") for _, _, rel in entries}
    # 사람 승인 장부. 표시가 검사 결과를 바꾸지는 않지만, 승인·미승인 상태를 구분해 보여 준다.
    from . import approvals as approvals_mod
    ledger = approvals_mod.load(cfg)
    approval_states = {rel: approvals_mod.page_status(ledger, rel, texts[rel]) for rel in texts}
    if settings.require_approval:
        blocked = sorted(rel for rel, state in approval_states.items() if state != "approved")
        if blocked:
            raise RuntimeError("site.require_approval: 사람 검토 승인이 없는 문서가 있어 게시를 중단합니다: "
                               + ", ".join(blocked) + " (`sdd accept <문서>` 로 승인 기록)")
    if "index.md" not in texts:
        intro = settings.intro
        if intro:
            texts["index.md"] = (cfg.root / str(intro)).read_text(encoding="utf-8")
        else:
            texts["index.md"] = "# 문서 안내\n\n코드에서 추출한 구조와 문장별 근거를 함께 확인하세요.\n"
        texts["index.md"] += "\n## 문서 검증 현황 {#문서-목록}\n\n"
        status_groups = {}
        for _, name, rel in entries:
            check_name, result, _ = _check(split_frontmatter(texts[rel])[0])
            label = _approval_label(approval_states.get(rel, "unreviewed"), ledger["pages"].get(rel))
            status_groups.setdefault((f'{check_name} {result}', label), []).append((name, rel))
        for (check, approval), pages in status_groups.items():
            summary = (f'<span>{html.escape(check)}</span> · <span>{html.escape(approval)}</span> '
                       f'(<span>{len(pages)}</span>)')
            texts['index.md'] += f'??? note "{summary}"\n' + ''.join(f'    - [{name}]({rel})\n' for name, rel in pages) + '\n'
        entries.insert(0, ("시작하기", "문서 안내", "index.md"))
        approval_states["index.md"] = "unreviewed"
    # 용어집은 표시용이다. 원고를 바꾸지 않고, 뜻이 없는 약어가 있으면 게시 전에 멈춘다.
    terms = glossary.load(cfg)
    if terms.terms and glossary.PAGE not in texts:
        texts[glossary.PAGE] = glossary.page(terms)
        after = next((i + 1 for i, e in enumerate(entries) if e[2] == "index.md"), 0)
        entries.insert(after, (entries[after - 1][0] if after else "시작하기", "용어집", glossary.PAGE))
        approval_states[glossary.PAGE] = "unreviewed"
    # 패키지 색인의 설명 열은 소스 주석을 그대로 옮긴 것이라 약어 검사에서 뺀다.
    glossary.enforce(cfg, terms, {rel: text for rel, text in texts.items()
                                  if sections.get(rel, {}).get("kind") != "per-package"})
    model = KnowledgeModel.load(cfg.facts_path) if cfg.facts_path.exists() else None
    if cfg.paths.get('consistency_file') and check_consistency:
        from .consistency import enforce as enforce_consistency
        if model is None:
            raise ValueError('facts.json is required for cross-document contract review')
        enforce_consistency(cfg, model)
    if model is None and any(s.get("kind", "prose") == "prose" and s.get("facts", {}).get("classes")
                            and cfg.diagram_policy(s).get("enabled", False)
                            for s in sections.values()):
        raise RuntimeError("facts.json is required to generate configured class diagrams")
    return texts, approval_states, ledger, terms, model


def _prepare_page_body(cfg, rel, texts, sections, terms, model):
    diagram_source = None
    meta, body = split_frontmatter(texts[rel])
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
        policy = cfg.diagram_policy(sc_section)
        scenario_document(sc, settings, int(policy.get("max_nodes", 16)))
        sources = re.findall(r"```mermaid\n(.*?)\n```", body, re.S)
        if len(sources) == 1:
            diagram_source = sources[0]
    page_title = _title_of_text(body)
    body = re.sub(r"^\s*# .+\n", "", body, count=1)
    section = sections.get(rel, {})
    if section and section.get("kind") != "manual":
        if section.get("design_requirements") or section.get("reader_profile"):
            from .design_contracts import enforce
            if model is None:
                raise RuntimeError("facts.json is required to verify design requirements")
            from . import generated_design
            if generated_design.enabled(section):
                generated_design.verify(model, section, texts[rel], cfg=cfg)
            else:
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
            diagram_source = diagram
            before, marker, after = body.partition('??? note "근거와 검토 정보"')
            # Move intact generated sections into reading order; preserve their wording.
            parts = re.fullmatch(r"(.*?)^(## 관련 클래스\n.*?)(^## 구조 설명\n.*)", before, re.S | re.M)
            if parts:
                body = parts[1] + parts[3] + block + parts[2] + marker + after
            else:
                body = before + block + marker + after
    if rel != glossary.PAGE and glossary.PAGE in texts:
        body = glossary.insert(body, glossary.block(glossary.used_terms(terms, texts[rel]),
                                                    posixpath.relpath(glossary.PAGE, posixpath.dirname(rel) or ".")))
    from .visuals import place
    from .generated_visuals import from_manuscript, render as render_visuals
    artifact = from_manuscript(cfg, model, section, texts[rel]) if section else None
    visuals = render_visuals(cfg, model, section, artifact) if section else []
    body = place(body, visuals, section)
    if rel == 'index.md' and cfg.site.overview_visual is not None:
        selection = cfg.site.overview_visual
        if (not isinstance(selection, dict) or set(selection) != {'section', 'visual'}
                or any(not isinstance(value, str) or not value for value in selection.values())):
            raise ValueError('site.overview_visual needs section and visual IDs')
        targets = [(path, value) for path, value in sections.items()
                   if value.get('id') == selection['section'] and path != 'index.md']
        if len(targets) != 1:
            raise ValueError('Overview visual source section is missing or ambiguous')
        target, original = targets[0]
        _, _, _, _, available = _prepare_page_body(cfg, target, texts, sections, terms, model)
        selected = [value for value in available if value[0]['id'] == selection['visual']]
        if len(selected) != 1 or not selected[0][2]:
            raise ValueError('Overview visual is missing or its source evidence changed')
        from .visuals import render_values
        # Revalidate the original definition and source pins for its new output
        # path; do not copy HTML, prose, stale diagrams or a model's answer.
        if any(value[0]['id'] == selection['visual'] for value in visuals):
            raise ValueError('Overview visual ID conflicts with an existing index visual')
        reused = render_values(cfg, model, {**original, 'output': 'index.md'}, [selected[0][0]])
        visuals += reused
        block = reused[0][1].replace('\n### ', '\n## ', 1)
        block = re.sub(r'\]\(#(source-[0-9a-f]{16})\)',
                       lambda match: '](' + target + '#' + match[1] + ')', block)
        first, separator, rest = body.lstrip('\n').partition('\n\n')
        body = first + '\n\n' + block + (separator + rest if separator else '')
    return page_title, meta, body, diagram_source, visuals


def _heading_search(items, page_title, rel):
    for item in items:
        yield {"title": html.unescape(re.sub("<[^>]+>", "", item["name"])),
               "page": page_title, "url": _html_path(rel) + "#" + quote(item["id"])}
        yield from _heading_search(item.get("children", []), page_title, rel)


def _render_pages(cfg, entries, sections, texts, terms, model, source_url, link_template):
    known = set(texts)
    rendered_pages = {}
    search = []
    diagram_sources = {}
    visual_sources = {}
    for group, name, rel in entries:
        page_title, meta, body, diagram, visuals = _prepare_page_body(cfg, rel, texts, sections, terms, model)
        if diagram is not None:
            diagram_sources[rel] = diagram
        for visual, _, source in visuals:
            if source:
                visual_sources[str(PurePosixPath(rel).with_suffix('')) + '.' + visual['id'] + '.mmd'] = source
        content, toc, tokens = _render(body, rel, known, model, source_url, str(meta.get("source_commit", "")),
                                       link_template)
        if sections.get(rel, {}).get('kind') == 'per-package':
            from .index_navigation import index_navigation
            content, symbols = index_navigation(content, _html_path(rel), page_title)
            search.extend(symbols)
        rendered_pages[rel] = (page_title, meta, content, toc)
        search.append({"title": page_title, "page": page_title, "url": _html_path(rel)})

        search.extend(_heading_search(tokens, page_title, rel))
    from .reading_cleanup import class_targets, link_related_classes
    targets = class_targets({_html_path(rel): page[2] for rel, page in rendered_pages.items()
                             if sections.get(rel, {}).get('kind') == 'per-package'})
    for rel, (page_title, meta, content, toc) in rendered_pages.items():
        if sections.get(rel, {}).get('kind', 'prose') == 'prose':
            rendered_pages[rel] = (page_title, meta, link_related_classes(content, _html_path(rel), targets), toc)
    return rendered_pages, search, diagram_sources, visual_sources


def _write_assets(cfg, out, mermaid_dir, visual_sources, terms):
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSETS, out / "assets", dirs_exist_ok=True)
    for rel, source in visual_sources.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source + '\n', encoding='utf-8', newline='\n')
    # 화면 자산이 바뀌면 주소도 바뀌게 한다. 그렇지 않으면 배포 직후 브라우저가 캐시한 예전 CSS·JS 로
    # 새 HTML 을 그려서, 새 기능이 깨진 모양으로 보인다.
    # 줄바꿈을 LF 로 맞춰 해시한다. 같은 커밋이면 Windows 작업 폴더(CRLF)에서도 같은 주소가 나온다.
    def _digest(parts: list[tuple[str, bytes]]) -> str:
        h = hashlib.sha256()
        for name, data in parts:
            h.update(name.encode() + b"\0" + data.replace(b"\r\n", b"\n") + b"\0")
        return h.hexdigest()[:10]

    asset_version = _digest([(p.name, p.read_bytes()) for p in sorted(ASSETS.iterdir()) if p.is_file()])
    # 용어 자료도 같은 이유로 주소에 해시를 붙인다. 영어판은 번역한 자료의 해시를 site_localization 이 붙인다
    # (번역 목록에는 이 페이지의 해시가 들어가므로, 여기서 번역 목록을 해시에 넣으면 순환한다).
    terms_version = _digest([("glossary", json.dumps(glossary.data(terms), ensure_ascii=False).encode())])
    if mermaid_dir:
        # Mermaid ESM 은 본체 옆 chunks/ 를 상대 경로로 불러오므로 디렉터리째 사이트에 담는다.
        # 그래야 CDN 없는 사내망·오프라인 열람에서도 그림이 뜬다. `sdd fetch-mermaid` 가 이 구조를 만든다.
        src_dir = (cfg.root / str(mermaid_dir)).resolve()
        if not (src_dir / MERMAID_ENTRY).is_file():
            raise RuntimeError(f"site.mermaid_dir 에 {MERMAID_ENTRY} 가 없습니다: {src_dir} "
                               "(`sdd fetch-mermaid` 로 준비하세요)")
        shutil.copytree(src_dir, out / "assets" / "mermaid", dirs_exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return asset_version, terms_version


def _navigation_html(entries, sections, rel, current):
    nav = []
    last_group = None
    last_section = None
    branch_open = False
    for nav_group, nav_title, nav_rel in entries:
        nav_section = _nav_section(nav_rel, sections)
        section_changed = (nav_group, nav_section) != last_section
        child = _is_child(nav_rel)
        if branch_open and (not child or section_changed):
            nav.append("</details>")
            branch_open = False
        if section_changed and last_section and last_section[1]:
            nav.append("</section>")
        if nav_group != last_group:
            if nav_group:
                nav.append(f'<p class="nav-group">{html.escape(nav_group)}</p>')
            last_group = nav_group
        if section_changed:
            if nav_section:
                nav.append(f'<section class="nav-section" aria-label="{html.escape(nav_section, quote=True)}">'
                           f'<h2>{html.escape(nav_section)}</h2>')
            last_section = (nav_group, nav_section)
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
    if last_section and last_section[1]:
        nav.append("</section>")
    return nav


def _pagination_html(entries, sections, index, rel, current):
    previous_next = []
    for offset, label in [(-1, "이전"), (1, "다음")]:
        other = index + offset
        fragment = ''
        if offset == 1 and sections.get(rel, {}).get('next', {}).get('link'):
            destination, _, requested_fragment = sections[rel]['next']['link'].partition('#')
            selected = next((i for i, entry in enumerate(entries) if entry[2] == (destination or rel)), None)
            if selected is not None:
                other, fragment = selected, requested_fragment
        if 0 <= other < len(entries):
            _, dest_title, dest_rel = entries[other]
            destination_href = _href(_html_path(dest_rel), current) + ('#' + quote(fragment) if fragment else '')
            previous_next.append(f'<a class="{"previous" if offset < 0 else "next"}" href="{destination_href}"><small>{label}</small>{html.escape(dest_title)} {"←" if offset < 0 else "→"}</a>')
    return previous_next


def _write_pages(cfg, out, entries, sections, rendered_pages, approval_states, ledger, diagram_sources,
                 mermaid_src, *, title, asset_version, terms_version):
    for index, (group, name, rel) in enumerate(entries):
        current = _html_path(rel)
        root = _href("index.html", current).removesuffix("index.html") or "./"
        page_title, meta, content, toc = rendered_pages[rel]
        nav = _navigation_html(entries, sections, rel, current)
        previous_next = _pagination_html(entries, sections, index, rel, current)
        from .reading_cleanup import merge_next_step
        for i, following in enumerate(previous_next):
            if following.startswith('<a class="next"'):
                content, previous_next[i] = merge_next_step(content, following)
        info = []
        method_label, method_scope = generation_info(str(meta.get("generation_method", "")))
        if meta:
            info.append(f'<dt>생성 방식</dt><dd>{html.escape(method_label)}</dd>')
            info.append(f'<dt>검증 범위</dt><dd>{html.escape(method_scope)}</dd>')
            check_name, check_result, check_scope = _check(meta)
            info.append(f'<dt>{check_name}</dt><dd>{check_result} (<code>{html.escape(str(meta.get("status", "unrecorded")))}</code>). '
                        f'{html.escape(check_scope)}</dd>')
        for key, label in [("source_commit", "분석 기준 커밋"), ("generated_at", "문서 생성 시각"), ("agent", "문장 생성 모델")]:
            if meta.get(key):
                info.append(f'<dt>{label}</dt><dd><code>{html.escape(str(meta[key]))}</code></dd>')
        downloads = ""
        if cfg.paths.get('consistency_file'):
            info.append('<dt>문서 간 계약</dt><dd><a href="' + _href('contract-consistency.json', current)
                        + '">자동 대조 보고서</a> · 사람 검토 전</dd>')
        section = sections.get(rel, {})
        if section.get('reader_scope'):
            info.append('<dt>독자 범위</dt><dd><a href="' + _href('reader-scope.json', current)
                        + '">과업별 답변과 미검토 범위</a></dd>')
        if any(t.get('_product_context') for t in section.get('design_topics', [])):
            info.append('<dt>제품 설명 입력</dt><dd><a href="' + _href('product-context.json', current)
                        + '">적용 범위·조건·자료</a></dd>')
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
            # 배지는 처음 읽는 사람용 짧은 말이다. 정확한 기록 문구와 상태 코드는 아래 생성 근거에 있다.
            status += (f'<span class="generation-method">작성: {html.escape(reader_label(str(meta.get("generation_method", ""))))}</span>'
                       '<a class="state-help" href="#page-evidence">상태 설명 ↓</a>')
        page_config = {"root": root, "mermaid": mermaid_src}
        if sections.get(rel, {}).get('kind') == 'per-package':
            page_config['index'] = True
        if glossary.PAGE in rendered_pages and rel != glossary.PAGE:
            page_config["terms"] = terms_version  # 본문의 첫 용어에 밑줄과 뜻 상자를 붙인다(site.js)
        config_json = json.dumps(page_config, ensure_ascii=False).replace("<", "\\u003c")
        doc = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title)} · {html.escape(title)}</title><link rel="stylesheet" href="{root}assets/reading.css?v={asset_version}"></head>
<body><a class="skip" href="#main">본문으로 이동</a>
<header class="site-header"><a class="brand" href="{root}index.html"><span class="brand-mark" aria-hidden="true">◉</span>{html.escape(title)}</a>
<div class="header-actions"><button id="search-open" hidden>문서 찾기 <kbd>Ctrl K</kbd></button><button id="menu-toggle" aria-controls="sidebar" aria-expanded="false" hidden>메뉴</button></div></header>
<div class="layout"><aside id="sidebar"><p class="edition">DESIGN DOCUMENTATION</p><nav aria-label="문서 메뉴">{''.join(nav)}</nav><p class="sidebar-note">코드에서 구조를 추출하고<br>근거와 함께 검토합니다.</p></aside>
<main id="main"><p class="breadcrumb">{html.escape(group)} <span>/</span> {html.escape(page_title)}</p><h1>{html.escape(page_title)}</h1><div class="page-state">{status}</div>
<details class="mobile-toc"><summary>이 페이지의 목차</summary>{toc}</details><article>{content}</article>{evidence}<nav class="pagination" aria-label="이전과 다음 문서">{''.join(previous_next)}</nav>
<footer>Generated by camera-hal-sdd-generator · 인용 검사와 사람의 내용 검토는 별도입니다.</footer></main>
<aside class="page-toc"><nav aria-label="현재 페이지 목차"><p>이 페이지에서</p>{toc}</nav></aside></div>
<dialog id="search-dialog" aria-labelledby="search-title"><div class="dialog-head"><h2 id="search-title">문서 찾기</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><label for="search-input">문서·절·용어·코드 요소 검색</label><input id="search-input" type="search" autocomplete="off" placeholder="예: Pipeline, IPA, 클래스 관계"><p id="search-count" role="status"></p><ul id="search-results"></ul></dialog>
<dialog id="diagram-dialog" aria-labelledby="diagram-title"><div class="dialog-head"><h2 id="diagram-title">클래스 관계</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><div class="diagram-tools"><label for="node-search">요소 찾기</label><input id="node-search" type="search" placeholder="그림 요소·함수 이름"><output id="node-count" aria-live="polite"></output><button id="zoom-out" aria-label="축소">−</button><output id="zoom-value">100%</output><button id="zoom-in" aria-label="확대">+</button><button id="zoom-fit">화면에 맞춤</button><button id="zoom-reset">100%</button></div><p class="diagram-pan-hint">그림이 화면보다 크면 가로·세로로 밀어 보세요. 전체 모양은 화면에 맞춤으로 확인합니다.</p><div id="diagram-viewport" tabindex="0" role="region" aria-label="확대된 다이어그램"><div id="diagram-canvas"></div></div></dialog>
<script id="site-config" type="application/json">{config_json}</script><script defer src="{root}assets/site.js?v={asset_version}"></script><script defer src="{root}assets/reader-tools.js?v={asset_version}"></script></body></html>'''
        target = out / current
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8", newline="\n")


def _write_search(out, rendered_pages, search, terms):
    if glossary.PAGE in rendered_pages:
        # 용어 이름으로도 찾게 하고, 본문 스크립트가 쓸 뜻 자료를 함께 둔다.
        search.extend(glossary.search_entries(terms, rendered_pages[glossary.PAGE][0]))
        (out / "assets" / "glossary.json").write_text(json.dumps(glossary.data(terms), ensure_ascii=False),
                                                      encoding="utf-8")
    (out / "assets" / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")


def _render_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None, *, check_consistency=True) -> Path:
    from .document_health import retired_paths
    retired = retired_paths(cfg)
    settings = cfg.site
    title = str(settings.title)
    source_url = str(settings.source_url)
    link_template = source_link_template(settings)
    # Mermaid 우선순위: --mermaid > site.mermaid > site.mermaid_dir(사이트에 동봉) > 공개 CDN.
    mermaid_dir = settings.mermaid_dir
    mermaid_src = mermaid_src or str(settings.mermaid or "")
    if not mermaid_src:
        mermaid_src = f"assets/mermaid/{MERMAID_ENTRY}" if mermaid_dir else MERMAID
    out = (out or cfg.build_dir / "site").resolve()
    if out == cfg.sdd_dir.resolve() or out in cfg.sdd_dir.resolve().parents:
        raise RuntimeError("Site output must be separate from the Markdown source directory")
    sections, entries = _site_navigation(cfg, settings, retired)
    texts, approval_states, ledger, terms, model = _prepare_site_pages(cfg, settings, sections, entries,
                                                                   check_consistency=check_consistency)
    rendered_pages, search, diagram_sources, visual_sources = _render_pages(
        cfg, entries, sections, texts, terms, model, source_url, link_template)
    asset_version, terms_version = _write_assets(cfg, out, mermaid_dir, visual_sources, terms)
    _write_pages(cfg, out, entries, sections, rendered_pages, approval_states, ledger, diagram_sources,
                 mermaid_src, title=title, asset_version=asset_version, terms_version=terms_version)
    _write_search(out, rendered_pages, search, terms)
    task_reports, product_reports = {}, {}
    for rel, section in sections.items():
        if section.get('reader_scope'):
            from . import generated_design
            from .design_contracts import enforce
            checked = (generated_design.verify(model, section, texts[rel], cfg=cfg)
                       if generated_design.enabled(section) else enforce(model, section))
            task_reports[rel] = checked['reader_scope']
            from .site_build import Page
            for detail in section['reader_scope']['optional']:
                target, _, anchor = detail['location'].partition('#')
                target = out / _html_path(target)
                if not target.is_file() or (anchor and anchor not in Page(target).ids):
                    raise ValueError('Reader optional detail target or anchor is missing: ' + detail['location'])
        contexts = {t['id']: t['_product_context'] for t in section.get('design_topics', [])
                    if '_product_context' in t}
        if contexts:
            product_reports[rel] = contexts
    for name, records in (('reader-scope', task_reports), ('product-context', product_reports)):
        if records:
            (out / (name + '.json')).write_text(json.dumps(
                {'schema': 1, 'source_commit': model.meta.get('source_commit'), 'pages': records},
                ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
    if cfg.paths.get('consistency_file') and check_consistency:
        shutil.copyfile(cfg.build_dir/'consistency-review.json', out/'contract-consistency.json')
    from .site_localization import localize_site
    localize_site(cfg, out)
    return out
