"""생성된 SDD 전체를 파일 하나짜리 HTML 로 만든다.

MkDocs 사이트를 띄울 수 없는 자리(메일 첨부, 리뷰 코멘트, 오프라인 열람)용이다.
페이지 순서는 mkdocs.yml 의 nav 를 따르고, 페이지 사이 링크는 같은 문서 안의 앵커로 바꾼다.
Mermaid 는 CDN(cdn.jsdelivr.net) 에서 받는다. 사내망에서 막히면 --mermaid 로 로컬 파일 경로를 준다.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import markdown
import yaml

from .config import Config

from .document_metadata import split_frontmatter as _split
_MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"

_CSS = """
:root { --fg:#1f2328; --muted:#59636e; --line:#d8dee4; --bg:#fff; --side:#f6f8fa; --ok:#1a7f37; --warn:#9a6700; --code:#f6f8fa; }
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"Segoe UI","Pretendard","Noto Sans KR",sans-serif; color:var(--fg); background:var(--bg); line-height:1.65; }
nav { position:fixed; top:0; left:0; bottom:0; width:280px; overflow:auto; background:var(--side); border-right:1px solid var(--line); padding:20px 16px; font-size:14px; }
nav h1 { font-size:15px; margin:0 0 14px; }
nav .group { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; margin:14px 0 4px; }
nav a { display:block; color:var(--fg); text-decoration:none; padding:4px 6px; border-radius:6px; }
nav a:hover { background:#eaeef2; }
nav a.sub { padding-left:18px; font-size:13px; }
main { margin-left:280px; padding:32px 48px 80px; max-width:980px; }
section.page { border-top:1px solid var(--line); padding-top:32px; margin-top:32px; }
section.page:first-child { border-top:0; margin-top:0; padding-top:0; }
h1 { font-size:28px; margin:0 0 6px; } h2 { font-size:20px; margin:28px 0 10px; border-bottom:1px solid var(--line); padding-bottom:4px; }
.meta { color:var(--muted); font-size:13px; margin-bottom:16px; }
.badge { display:inline-block; font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid; margin-right:6px; }
.badge.ok { color:var(--ok); border-color:var(--ok); } .badge.needs-review { color:var(--warn); border-color:var(--warn); }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }
th, td { border:1px solid var(--line); padding:6px 10px; text-align:left; vertical-align:top; }
th { background:var(--side); }
code { background:var(--code); padding:1px 5px; border-radius:4px; font-size:.92em; }
pre { background:var(--code); padding:12px; overflow:auto; border-radius:6px; }
pre.mermaid { background:#fff; border:1px solid var(--line); text-align:center; }
details { border:1px solid var(--line); border-radius:6px; padding:8px 12px; margin:16px 0; background:var(--side); }
summary { cursor:pointer; font-weight:600; }
p.lead { font-weight:600; font-size:16px; }
@media (max-width: 860px) { nav { position:static; width:auto; border-right:0; border-bottom:1px solid var(--line); } main { margin:0; padding:16px; } }
"""


def _mermaid_fence(source: str, language: str, css_class: str, options: dict, md: Any, **kwargs: Any) -> str:
    return f'<pre class="mermaid">{html.escape(source)}</pre>'


def _page_id(rel: str) -> str:
    return "page-" + re.sub(r"[^a-z0-9]+", "-", rel.lower().removesuffix(".md")).strip("-")


def _nav_entries(mkdocs_yml: Path, sdd_dir: Path) -> list[tuple[str, str, str]]:
    """(그룹, 제목, 상대 경로) 목록. nav 가 없으면 파일 순서."""
    out: list[tuple[str, str, str]] = []
    if mkdocs_yml.exists():
        data = yaml.load(mkdocs_yml.read_text(encoding="utf-8"), Loader=_LenientLoader) or {}

        def walk(items: Any, group: str) -> None:
            for it in items or []:
                if isinstance(it, dict):
                    for title, val in it.items():
                        if isinstance(val, str):
                            out.append((group, str(title), val))
                        else:
                            walk(val, str(title))
        walk(data.get("nav"), "")
    if not out:
        for p in sorted(sdd_dir.rglob("*.md")):
            rel = p.relative_to(sdd_dir).as_posix()
            # 시나리오 하위 페이지는 아래에서 제목과 순서를 붙여 넣는다. 여기서 파일 이름으로
            # 먼저 넣으면 목차에 stem 이 제목으로 남는다.
            if rel.startswith("scenarios/") and rel != "scenarios/index.md":
                continue
            out.append(("", p.stem, rel))
    # 시나리오 개별 페이지는 nav 에 없으므로 index 뒤에 붙인다.
    scen_dir = sdd_dir / "scenarios"
    if scen_dir.exists():
        idx = next((i for i, e in enumerate(out) if e[2] == "scenarios/index.md"), None)
        # 그룹은 비워서 시나리오 목차와 같은 그룹에 딸리게 한다.
        extra = [("", _title_of(p), f"scenarios/{p.name}") for p in sorted(scen_dir.glob("*.md")) if p.name != "index.md"]
        if idx is not None:
            out[idx + 1:idx + 1] = extra
        else:
            out += extra
    return out


class _LenientLoader(yaml.SafeLoader):
    """mkdocs.yml 의 !!python/name 태그를 무시한다."""


_LenientLoader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def _title_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^# (.+)$", text, re.M)
    return m.group(1).strip() if m else path.stem



def render_page(rel: str, text: str, known: set[str]) -> str:
    meta, body = _split(text)
    pid = _page_id(rel)
    # frontmatter 뒤에 빈 줄이 오므로 앞 공백을 허용한다. 제목은 페이지 헤더가 따로 붙인다.
    body = re.sub(r"^\s*# .+\n", "", body, count=1)
    title = _title_of_text(text)

    def slug(value: str, sep: str) -> str:
        s = re.sub(r"[^\w\s-]", "", value.strip().lower())
        return f"{pid}--" + re.sub(r"[-\s]+", sep, s)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list", "pymdownx.details",
                                       "pymdownx.superfences"],
                           extension_configs={
                               "toc": {"slugify": slug},
                               "pymdownx.superfences": {"custom_fences": [
                                   {"name": "mermaid", "class": "mermaid", "format": _mermaid_fence}]},
                           })
    out = md.convert(body)

    # 페이지 사이 링크 -> 같은 문서의 앵커. 같은 페이지 앵커 -> 접두사 붙인 앵커.
    base_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""

    def fix_href(m: re.Match[str]) -> str:
        href = m.group(1)
        if href.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        if href.startswith("#"):
            return f'href="#{pid}--{href[1:]}"'
        target, _, anchor = href.partition("#")
        joined = _norm(f"{base_dir}/{target}" if base_dir and not target.startswith("/") else target)
        if joined in known:
            return f'href="#{_page_id(joined)}{("--" + anchor) if anchor else ""}"'
        return m.group(0)

    out = re.sub(r'href="([^"]+)"', fix_href, out)
    out = re.sub(r"<p><strong>(.+?)</strong></p>", r'<p class="lead"><strong>\1</strong></p>', out, count=1)

    status = str(meta.get("status", ""))
    badge = f'<span class="badge {status}">{status}</span>' if status else ""
    extra = " · ".join(f"{k}: {html.escape(str(v))}" for k, v in meta.items()
                       if k in ("source_commit", "agent", "generated_at") and v)
    return (f'<section class="page" id="{pid}"><h1>{html.escape(title)}</h1>'
            f'<div class="meta">{badge}{extra}</div>{out}</section>')


def _title_of_text(text: str) -> str:
    m = re.search(r"^# (.+)$", text, re.M)
    return m.group(1).strip() if m else "(제목 없음)"


def _norm(p: str) -> str:
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def export(cfg: Config, out: Path | None = None, mkdocs_yml: Path | None = None,
           mermaid_src: str = _MERMAID_CDN, site_name: str = "Camera HAL SDD",
           pages: list[str] | None = None) -> Path:
    """pages: sdd 루트 기준 상대 경로 목록. 주면 그 페이지만 담는다 (리뷰 코멘트에 한 절만 붙일 때, 스크린샷용)."""
    sdd_dir = cfg.sdd_dir
    entries = _nav_entries(mkdocs_yml or cfg.root / "mkdocs.yml", sdd_dir)
    entries = [e for e in entries if (sdd_dir / e[2]).exists()]
    known = {e[2] for e in entries}          # 링크 대상은 전체 페이지 기준으로 남긴다
    if pages:
        wanted = {p.replace("\\", "/") for p in pages}
        entries = [e for e in entries if e[2] in wanted]

    nav_html: list[str] = []
    sections: list[str] = []
    last_group = None
    for group, title, rel in entries:
        if group != last_group and group:
            nav_html.append(f'<div class="group">{html.escape(group)}</div>')
            last_group = group
        text = (sdd_dir / rel).read_text(encoding="utf-8")
        meta, _ = _split(text)
        status = str(meta.get("status", ""))
        dot = f' <span class="badge {status}">{status}</span>' if status else ""
        cls = ' class="sub"' if rel.startswith("scenarios/") and rel != "scenarios/index.md" else ""
        nav_html.append(f'<a{cls} href="#{_page_id(rel)}">{html.escape(title)}{dot}</a>')
        sections.append(render_page(rel, text, known))

    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(site_name)}</title><style>{_CSS}</style></head>
<body><nav><h1>{html.escape(site_name)}</h1>{''.join(nav_html)}</nav>
<main>{''.join(sections)}</main>
<script type="module">import mermaid from "{mermaid_src}"; mermaid.initialize({{ startOnLoad: true, securityLevel: "loose" }});</script>
</body></html>"""
    out = out or (cfg.build_dir / "sdd.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8", newline="\n")
    return out
