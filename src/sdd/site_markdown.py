"""Shared Markdown presentation for publication and displayed contract review."""
from __future__ import annotations
import html
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import quote,urlsplit
import markdown
from .evidence_navigation import compact_evidence, fold_source_details
from .export_html import _mermaid_fence
from .facts.model import KnowledgeModel
SOURCE_LINK_TEMPLATES = {
    "github": "{url}/blob/{commit}/{file}#L{line}",
    "gitiles": "{url}/+/{commit}/{file}#{line}",
}

def _href(rel: str, current: str) -> str:
    return quote(posixpath.relpath(rel, posixpath.dirname(current) or "."), safe="/.-")


def _html_path(rel: str) -> str:
    return str(PurePosixPath(rel).with_suffix(".html"))



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
        product_citations = {f"{r['file']}:{r['line']}" for r in model.evidence.values()
                             if r.get('origin') == 'product-material'}

        def citation(match: re.Match) -> str:
            cite = html.unescape(match[1])
            if cite not in valid:
                return match[0]
            if cite in product_citations:
                return match[0]
            file, line = cite.rsplit(":", 1)
            if PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts:
                return match[0]
            url = link_template.format(url=source_url.rstrip("/"), commit=commit,
                                       file=quote(file, safe="/"), line=line)
            return f'<a class="citation" href="{html.escape(url, quote=True)}">{match[0]}</a>'

        rendered = re.sub(r"<code>([^<>]+:\d+)</code>", citation, rendered)
    valid = model.citations() if model and commit == model.meta.get("source_commit") else set()
    rendered = compact_evidence(rendered, valid)
    rendered = fold_source_details(rendered)

    def table_wrapper(match: re.Match) -> str:
        table = match[0]
        # Navigation choices must remain visible without horizontal scrolling.
        routes = any(f'<th>{heading}</th>' in table for heading in ('지금 확인할 내용', '시작할 문서'))
        head = re.search(r"<thead>(.*?)</thead>", table, re.S)
        labels = [html.escape(html.unescape(re.sub(r"<[^>]+>", "", cell)).strip(), quote=True)
                  for cell in re.findall(r"<th[^>]*>(.*?)</th>", head[1], re.S)] if head else []
        if routes:
            classes = 'table-scroll reading-routes'
        elif len(labels) >= 3:
            # 휴대폰에서는 세 열 이상 표를 행마다 열 이름이 붙은 묶음으로 쌓아, 가로로 밀지 않고 읽게 한다(reading.css).
            classes = 'table-scroll stack'

            def row(match: re.Match) -> str:
                cells = iter(labels)
                return re.sub(r"<td(?=[\s>])", lambda _: f'<td data-label="{next(cells, "")}"', match[0])

            table = re.sub(r"<tr>.*?</tr>", row, table, flags=re.S)
        else:
            classes = 'table-scroll'
        return f'<div class="{classes}" tabindex="0" role="region" aria-label="표">{table}</div>'

    rendered = re.sub(r"<table>.*?</table>", table_wrapper, rendered, flags=re.S)
    return rendered, md.toc, md.toc_tokens

