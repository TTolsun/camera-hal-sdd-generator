"""Print and Markdown copies of each published page and the whole document.

Both copies are assembled from the final page HTML, after review records, navigation links and
translation have been applied, so they contain exactly what a reader sees on the site. Nothing is
regenerated and no manuscript is re-read. Folded `details` are opened, page-local IDs are prefixed
per page, and links between pages become links inside the one document.

The Markdown conversion records every text node it writes. A text node that no rule consumed stops
the build instead of shipping a copy with silently missing content.
"""
from __future__ import annotations

import html
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

from .site_markdown import _html_path
from .site_paths import owned_path

DIRECTORY = 'download'
PRINT_PAGE = 'full.html'
MARKDOWN = 'full.md'

LABELS = {
    'ko': dict(menu_label='Download the whole document', pdf='PDF', markdown='Markdown',
               pdf_action='전체 문서를 PDF로 인쇄', md_action='전체 문서를 Markdown으로 다운로드', heading='전체 문서', pages='{count}편', commit='분석 기준 커밋', site='원본 사이트', contents='목차',
               notice=('이 파일은 사이트의 모든 문서를 하나로 묶은 사본입니다. 만든 뒤에 바뀐 코드와 문서는 반영되지 않으므로 '
                       '분석 기준 커밋을 함께 확인하세요. 인용 검사 같은 자동 검사 결과는 사람 검토 승인이 아닙니다. '
                       '문서별 검토 상태는 각 문서 끝의 문서 생성·검토 정보에 있습니다.'),
               back='사이트로 돌아가기', save='Save as PDF', save_markdown='Download Markdown', preparing='그림을 그리는 중입니다.',
               hint='인쇄 창에서 대상을 PDF로 저장(Save as PDF)으로 선택하세요.'),
    'en': dict(menu_label='Download the whole document', pdf='PDF',
               markdown='Markdown', pdf_action='Print the whole document to PDF', md_action='Download the whole document as Markdown', heading='Whole document', pages='{count} pages',
               commit='Analyzed source commit', site='Source site', contents='Contents',
               notice=('This file combines every page of the site into one copy. Code and documents changed after it '
                       'was made are not included, so check the analyzed source commit. Automated checks such as '
                       'citation checks are not human review approval. Each page ends with its generation and review '
                       'record.'),
               back='Back to the site', save='Save as PDF', save_markdown='Download Markdown', preparing='Drawing diagrams.',
               hint='In the print dialog, choose Save as PDF as the destination.'),
}


# Inline so the shared site assets (reading.css, site.js) stay byte-identical; changing them
# invalidates reuse of every reviewed visual item on every page (visual_review_reuse).
STYLE = (
    '.full-document-bar{position:sticky;top:0;z-index:10;display:flex;flex-wrap:wrap;align-items:center;gap:8px 20px;'
    'padding:10px max(16px,calc((100vw - 900px)/2));background:#fff;border-bottom:1px solid var(--line);font-size:14px}'
    '.full-document-bar p{margin:0;color:var(--muted)}.full-actions{display:flex;flex-wrap:wrap;align-items:center;'
    'gap:8px 16px;margin-left:auto}.full-document-bar .full-hint{flex:1 1 100%;font-size:12px}'
    '#print-document{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}'
    '#print-document:disabled{background:var(--soft);border-color:var(--line);color:var(--muted);cursor:progress}'
    '.full-document main{max-width:900px;margin:0 auto;padding:32px 16px 64px}'
    '.full-cover dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 16px;font-size:14px}'
    '.full-cover dd{margin:0}.full-notice{border-left:3px solid #8ba99e;padding:4px 0 4px 14px;color:var(--muted);'
    'font-size:14px}.full-contents ol ol{padding-left:20px}'
    '.full-page{border-top:2px solid var(--line);margin-top:56px;padding-top:8px}.full-page>.breadcrumb{margin-bottom:0}'
    # Printing never hides content: long code wraps and wide diagrams shrink to the page.
    '@media print{.full-document-bar{display:none}.full-document main{padding:0;max-width:none}'
    '.full-cover{break-after:page}.full-page{break-before:page;border:0;margin:0;padding:0}'
    'pre{white-space:pre-wrap;overflow:visible}pre code{overflow-wrap:anywhere}'
    '.mermaid{overflow:visible;break-inside:avoid}.mermaid svg{max-width:100%!important;height:auto!important}'
    '.full-page details>summary{list-style:none}.full-page details>summary::-webkit-details-marker{display:none}}'
)

# Draw every diagram before printing; printing earlier would put Mermaid source text in the PDF.
# The Mermaid settings match the site pages (site_assets/site.js).
SCRIPT = """(() => {
  'use strict';
  const config = JSON.parse(document.querySelector('#site-config').textContent);
  const english = config.language === 'en';
  const t = (ko, en) => english ? en : ko;
  const root = new URL(config.root, location.href);
  const button = document.querySelector('#print-document');
  const status = document.querySelector('#print-status');
  const diagrams = [...document.querySelectorAll('.mermaid')];
  button.addEventListener('click', () => window.print());
  function finish(failed) {
    button.disabled = false;
    status.textContent = failed
      ? t(`그림 ${failed}개를 그리지 못해 Mermaid 원문으로 표시합니다. 원문도 PDF에 포함됩니다.`,
          `${failed} diagram(s) could not be drawn and are shown as Mermaid source, which the PDF includes.`)
      : t(`인쇄 준비가 끝났습니다. 그림 ${diagrams.length}개를 모두 그렸습니다.`,
          `Ready to print. All ${diagrams.length} diagram(s) are drawn.`);
    if (new URLSearchParams(location.search).has('print')) window.print();
  }
  if (!diagrams.length) { finish(0); return; }
  import(new URL(config.mermaid, root).href).then(async ({default: mermaid}) => {
    mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base',
      themeVariables: {background: '#ffffff', primaryColor: '#edf5f1', primaryTextColor: '#17201e',
        primaryBorderColor: '#8ba99e', lineColor: '#66766f', secondaryColor: '#f6f7f8',
        tertiaryColor: '#ffffff', edgeLabelBackground: '#ffffff',
        fontFamily: 'Geist, Malgun Gothic, system-ui, sans-serif', fontSize: '14px'},
      flowchart: {htmlLabels: false, curve: 'basis', nodeSpacing: 38, rankSpacing: 65, padding: 16}});
    let failed = 0;
    // Hide the long body while drawing: otherwise every render re-lays out the whole document
    // (31 pages took over six minutes for 164 diagrams; hidden, about five seconds).
    // Mermaid measures text in its own container under body, so sizes are unaffected.
    const body = document.querySelector('main');
    body.style.display = 'none';
    try {
    for (const [i, diagram] of diagrams.entries()) {
      status.textContent = t(`그림을 그리는 중입니다 (${i + 1}/${diagrams.length}). 다 그리면 본문을 표시합니다.`,
                             `Drawing diagrams (${i + 1}/${diagrams.length}). The document appears when they are done.`);
      const source = diagram.textContent;
      try {
        const {svg} = await mermaid.render(`sdd-print-${i}`, source);
        diagram.innerHTML = svg;
        diagram.dataset.ready = 'true';
      } catch (_) {
        failed += 1;
        diagram.textContent = source;
        diagram.classList.add('diagram-error');
      }
    }
    } finally {
      body.style.display = '';
    }
    finish(failed);
  }).catch(() => finish(diagrams.length));
})();"""


def paths(english: bool) -> tuple[str, str]:
    prefix = ('en/' if english else '') + DIRECTORY + '/'
    return prefix + PRINT_PAGE, prefix + MARKDOWN


def is_combined(rel: str) -> bool:
    """The combined copies repeat every page; per-page audits must not count them twice."""
    return rel in {paths(False)[0], paths(True)[0]}


def page_paths(page: str, english: bool) -> tuple[str, str]:
    prefix = 'en/' if english else ''
    printable = prefix + DIRECTORY + '/pages/' + page.removeprefix(prefix)
    return printable, posixpath.splitext(printable)[0] + '.md'


def reader_html_files(root, files):
    """Exclude generated print views from reader inventories, while still checking their links."""
    files = set(files)
    copies = {rel for rel in files if is_combined(rel)}
    for page in files:
        english = page.startswith('en/')
        printable, _ = page_paths(page, english)
        if paths(english)[0] in files and printable in files:
            with owned_path(root, printable).open('rb') as stream:
                if stream.read(96).startswith(b'<!doctype html>\n<html data-sdd-page-copy '):
                    copies.add(printable)
    return files - copies


def download_name(title: str, english: bool) -> str:
    stem = re.sub(r'[\\/:*?"<>|\s]+', '-', title).strip('-.') or 'sdd'
    return stem + ('.en' if english else '') + '.md'


# ---------------------------------------------------------------- page assembly

def _single(pattern: str, text: str, rel: str, what: str) -> re.Match:
    found = list(re.finditer(pattern, text, re.S))
    if len(found) != 1:
        raise RuntimeError(f'Whole document: expected one {what} in {rel}, found {len(found)}')
    return found[0]


def _page_parts(document: str, rel: str) -> tuple[str, str, str]:
    """Return (group, title, readable HTML) from one generated page."""
    start = _single(r'<main id="main">', document, rel, 'main').end()
    end = _single(r'<nav class="pagination"', document, rel, 'pagination').start()
    body = document[start:end]
    _single(r'<article>', body, rel, 'article')
    group = re.search(r'<p class="breadcrumb">(.*?) <span>/</span>', body, re.S)
    title = _single(r'<h1>(.*?)</h1>', body, rel, 'title')[1]
    body = re.sub(r'<p class="breadcrumb">.*?</p>', '', body, count=1, flags=re.S)
    body = re.sub(r'<details class="mobile-toc">.*?</details>', '', body, count=1, flags=re.S)
    return (group[1] if group else ''), title, body


_ID_ATTRS = re.compile(r'(\s)(id|for|aria-controls|aria-labelledby|aria-describedby)="([^"]*)"')
_URL_ATTRS = re.compile(r'(\s)(href|src)="([^"]*)"')


def _rewrite(body: str, page: str, number: int, page_numbers: dict[str, int], directory: str) -> str:
    prefix = f'd{number}-'
    body = _ID_ATTRS.sub(lambda m: f'{m[1]}{m[2]}="' + ' '.join(prefix + value for value in m[3].split()) + '"', body)

    def url(match):
        value = html.unescape(match[3])
        parts = urlsplit(value)
        if parts.scheme or parts.netloc or value.startswith('/'):
            return match[0]
        if not parts.path:
            new = '#' + prefix + parts.fragment if parts.fragment else '#doc-' + str(number)
        else:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(parts.path)))
            if target in page_numbers:
                other = page_numbers[target]
                new = f'#d{other}-{parts.fragment}' if parts.fragment else f'#doc-{other}'
            else:
                new = quote(posixpath.relpath(target, directory), safe='/')
                new += ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
        return f'{match[1]}{match[2]}="{html.escape(new, quote=True)}"'

    body = _URL_ATTRS.sub(url, body)
    # Nothing folded may be missing from a printed or saved copy.
    return re.sub(r'<details(?![^>]*\sopen[\s>=])', '<details open', body)


def _config(document: str, page: str, directory: str) -> dict:
    data = json.loads(_single(r'<script id="site-config" type="application/json">(.*?)</script>',
                              document, page, 'site configuration')[1])
    root = posixpath.normpath(posixpath.join(posixpath.dirname(page), data['root']))
    data['root'] = posixpath.relpath(root, directory).rstrip('/') + '/'
    return {key: data[key] for key in ('root', 'mermaid', 'language') if key in data}


def _stylesheet(document: str, page: str, directory: str) -> str:
    href = html.unescape(_single(r'<link rel="stylesheet" href="([^"]+)">', document, page, 'stylesheet')[1])
    parts = urlsplit(href)
    target = posixpath.normpath(posixpath.join(posixpath.dirname(page), parts.path))
    return posixpath.relpath(target, directory) + ('?' + parts.query if parts.query else '')


def _print_view(original, page, print_path, english, heading, content, back, md_href, name, *, single=False):
    text = LABELS['en' if english else 'ko']
    directory = posixpath.dirname(print_path)
    css = _stylesheet(original, page, directory)
    config = _config(original, page, directory)
    marker = ' data-sdd-page-copy' if single else ''
    page_style = '.full-page{margin:0;border:0;padding:0;break-before:auto}' if single else ''
    return f'''<!doctype html>
<html{marker} lang="{'en' if english else 'ko'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading}</title><link rel="stylesheet" href="{html.escape(css, quote=True)}"><style>{STYLE}{page_style}</style></head>
<body class="full-document"><div class="full-document-bar"><a href="{html.escape(back, quote=True)}">← {text["back"]}</a><p id="print-status" role="status">{text["preparing"]}</p>
<div class="full-actions"><button id="print-document" type="button" disabled>{text["save"]}</button><a href="{html.escape(md_href, quote=True)}" download="{html.escape(name, quote=True)}">{text["save_markdown"]}</a></div><p class="full-hint">{text["hint"]}</p></div>
<main id="main">{content}</main>
<script id="site-config" type="application/json">{json.dumps(config, ensure_ascii=False).replace("<", chr(92) + "u003c")}</script><script>{SCRIPT}</script></body></html>
'''


def _page_copy(original, page, english, public_url):
    print_path, markdown_path = page_paths(page, english)
    directory = posixpath.dirname(print_path)
    _, title, body = _page_parts(original, page)
    content = ('<section class="full-page" id="doc-1">'
               + _rewrite(body, page, 1, {page: 1}, directory) + '</section>')
    back = quote(posixpath.relpath(page, directory))
    md_href = quote(posixpath.basename(markdown_path))
    filename = download_name(posixpath.splitext(posixpath.basename(page))[0], english)
    document = _print_view(original, page, print_path, english, title, content, back, md_href, filename, single=True)
    base = public_url.rstrip('/') + '/' + quote(directory) + '/' if public_url else ''
    return document, to_markdown(content, base_url=base)


def _combined(pages, *, english, site_title, source_commit, public_url):
    """pages: [(out-relative html path, page document)] in reading order."""
    text = LABELS['en' if english else 'ko']
    print_path, markdown_path = paths(english)
    directory = posixpath.dirname(print_path)
    numbers = {rel: index for index, (rel, _) in enumerate(pages, 1)}
    sections, contents, last_group = [], [], None
    for rel, document in pages:
        group, title, body = _page_parts(document, rel)
        number = numbers[rel]
        if group != last_group:
            if contents:
                contents.append('</ol></li>')
            contents.append(f'<li>{group}<ol>' if group else '<li><ol>')
            last_group = group
        contents.append(f'<li><a href="#doc-{number}">{title}</a></li>')
        sections.append(f'<section class="full-page" id="doc-{number}">'
                        + (f'<p class="breadcrumb">{group}</p>' if group else '')
                        + _rewrite(body, rel, number, numbers, directory) + '</section>')
    if contents:
        contents.append('</ol></li>')
    site_link = ''
    if public_url:
        site = public_url.rstrip('/') + '/' + ('en/' if english else '')
        site_link = f'<dt>{text["site"]}</dt><dd><a href="{html.escape(site, quote=True)}">{html.escape(site)}</a></dd>'
    commit = (f'<dt>{text["commit"]}</dt><dd><code>{html.escape(source_commit)}</code></dd>' if source_commit else '')
    heading = f'{html.escape(site_title)} · {text["heading"]}'
    name = download_name(site_title, english)
    content = (f'<section class="full-cover"><h1>{heading}</h1><p>{text["pages"].format(count=len(pages))}</p>'
               f'<dl>{commit}{site_link}</dl><p class="full-notice">{html.escape(text["notice"])}</p>'
               f'<nav class="full-contents" aria-labelledby="full-contents-title"><h2 id="full-contents-title">'
               f'{text["contents"]}</h2><ol>{"".join(contents)}</ol></nav></section>' + ''.join(sections))
    back = posixpath.relpath('en/index.html' if english else 'index.html', directory)
    document = _print_view(pages[0][1], pages[0][0], print_path, english, heading, content, back,
                           posixpath.basename(markdown_path), name)
    base = public_url.rstrip('/') + '/' + directory + '/' if public_url else ''
    markdown = to_markdown(content, base_url=base)
    return document, markdown


def _icon(path: str, size: int) -> str:
    return (f'<svg aria-hidden="true" focusable="false" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="currentColor"><path d="{path}"></path></svg>')


# Self-contained toolbar artwork stays available in offline copies.
_DOWNLOAD_ICON = _icon('M10 2h4v8h4l-6 6-6-6h4z M3 15h3v4h12v-4h3v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 20)
_FILE_ICON = _icon('M5 2h9l5 5v15H5z M13 4v5h5z M8 13v2h8v-2z M8 17v2h6v-2z', 16)


def _menu(page: str, english: bool, filename: str, *, whole_only=False) -> str:
    text = LABELS['en' if english else 'ko']
    print_path, markdown_path = paths(english)
    here = posixpath.dirname(page) or '.'
    label = text['menu_label'] if whole_only else 'Download'
    # The native popover provides keyboard activation, Escape and outside-click dismissal.
    # With no anchor positioning support, the popover uses the browser's centered placement.
    row = 'display:flex;align-items:center;gap:.65rem;padding:.35rem .65rem;color:inherit;text-decoration:none'

    def group(heading, printable, markdown, name, pdf_label, md_label):
        pdf = html.escape(quote(posixpath.relpath(printable, here)) + '?print', quote=True)
        md = html.escape(quote(posixpath.relpath(markdown, here)), quote=True)
        return (f'<strong style="display:block;padding:.2rem .65rem;color:var(--muted);font-size:12px">{heading}</strong>'
                f'<a href="{pdf}" title="{pdf_label}" aria-label="{pdf_label}" style="{row}">{_FILE_ICON}.pdf</a>'
                f'<a href="{md}" download="{html.escape(name, quote=True)}" title="{md_label}" '
                f'aria-label="{md_label}" style="{row}">{_FILE_ICON}.md</a>')

    groups = group(text['heading'], print_path, markdown_path, filename, text['pdf_action'], text['md_action'])
    if not whole_only:
        this_page = group('Current page' if english else '현재 페이지', *page_paths(page, english),
                          download_name(posixpath.splitext(posixpath.basename(page))[0], english),
                          'Print this page to PDF' if english else '현재 페이지를 PDF로 인쇄',
                          'Download this page as Markdown' if english else '현재 페이지를 Markdown으로 다운로드')
        groups = this_page + '<hr style="border:0;border-top:1px solid var(--line);margin:.25rem 0">' + groups
    return (f'<nav class="download-nav" aria-label="{label}" style="display:flex;align-items:center">'
            f'<button type="button" popovertarget="download-menu" title="{label}" '
            f'aria-label="{label}" style="anchor-name:--sdd-download;display:grid;place-items:center;'
            f'width:40px;height:40px;padding:0;border:0;color:var(--muted)">{_DOWNLOAD_ICON}</button>'
            f'<div id="download-menu" popover="auto" style="position-anchor:--sdd-download;'
            f'inset:auto anchor(right) auto auto;top:anchor(bottom);margin:auto;padding:.4rem;'
            f'min-width:9rem;background:white;color:var(--ink);border:1px solid var(--line);'
            f'border-radius:6px;box-shadow:0 4px 12px #17201e20;font-size:14px">'
            f'{groups}</div></nav>')


def publish(out: Path, entries, *, site_title: str, source_commit: str = '', public_url: str = '') -> None:
    """Write current-page and whole-document exports for every available edition."""
    for english in (False, True):
        prefix = 'en/' if english else ''
        if english and not (out / 'en').is_dir():
            continue
        print_path, markdown_path = paths(english)
        if (out / print_path).exists() or (out / markdown_path).exists():
            raise RuntimeError(f'Whole document path is already used by a page: {print_path}')
        pages = []
        for _, _, rel in entries:
            page = prefix + _html_path(rel)
            if not (out / page).is_file():
                raise RuntimeError(f'Whole document: generated page is missing: {page}')
            pages.append((page, (out / page).read_text(encoding='utf-8')))
        # The header brand is the edition's displayed site name, translated for English.
        brand = re.search(r'<a class="brand"[^>]*>(?:<span[^>]*>.*?</span>)?(.*?)</a>', pages[0][1], re.S)
        edition_title = html.unescape(brand[1]).strip() if brand and brand[1].strip() else site_title
        document, markdown = _combined(pages, english=english, site_title=edition_title,
                                       source_commit=source_commit, public_url=public_url)
        (out / print_path).parent.mkdir(parents=True, exist_ok=True)
        (out / print_path).write_text(document, encoding='utf-8', newline='\n')
        (out / markdown_path).write_text(markdown, encoding='utf-8', newline='\n')
        for page, original in pages:
            printable, md = page_paths(page, english)
            if (out / printable).exists() or (out / md).exists():
                raise RuntimeError(f'Page download path already in use: {printable} or {md}')
            page_html, page_markdown = _page_copy(original, page, english, public_url)
            (out / printable).parent.mkdir(parents=True, exist_ok=True)
            (out / printable).write_text(page_html, encoding='utf-8', newline='\n')
            (out / md).write_text(page_markdown, encoding='utf-8', newline='\n')
            marker = '<button id="search-open"'
            if original.count(marker) != 1:
                raise RuntimeError(f'Whole document: header actions are missing in {page}')
            (out / page).write_text(original.replace(marker, _menu(page, english, download_name(site_title, english)) + marker, 1),
                                    encoding='utf-8', newline='\n')


# ---------------------------------------------------------------- HTML to Markdown

class _Text:
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value


class _Node:
    __slots__ = ('tag', 'attrs', 'children')

    def __init__(self, tag, attrs=None, children=None):
        self.tag, self.attrs = tag, attrs or {}
        self.children = [_Text(c) if isinstance(c, str) else c for c in (children or [])]


BLOCKS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'pre', 'table', 'details', 'blockquote', 'dl', 'hr',
          'section', 'article', 'div', 'main', 'nav', 'header', 'footer', 'figure', 'aside', 'summary', 'figcaption'}
SKIPPED = {'script', 'style', 'template', '!'}
VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'wbr'}
_STRUCTURE = {'ul', 'ol', 'pre', 'table', 'details', 'dl', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}


def _text_nodes(node):
    for child in node.children:
        if isinstance(child, _Text):
            yield child
        elif child.tag not in SKIPPED:
            yield from _text_nodes(child)


class _Markdown:
    def __init__(self, referenced: set[str], base_url: str):
        self.referenced, self.base_url = referenced, base_url
        self.written: set[int] = set()
        self.in_table = False

    # -- text helpers
    def plain_text(self, node) -> str:
        parts = []
        for text in _text_nodes(node):
            self.written.add(id(text))
            parts.append(text.value)
        return ''.join(parts)

    @staticmethod
    def escape(value: str) -> str:
        value = re.sub(r'([\\`*\[\]<>|~])', r'\\\1', value)
        return re.sub(r'(?<![0-9A-Za-z])_|_(?![0-9A-Za-z])', r'\\_', value)

    def anchor(self, node) -> str:
        identifier = node.attrs.get('id')
        return f'<a id="{html.escape(identifier, quote=True)}"></a>' if identifier in self.referenced else ''

    # -- inline
    def inline(self, nodes) -> str:
        parts = []
        for node in nodes:
            if isinstance(node, _Text):
                self.written.add(id(node))
                parts.append(self.escape(re.sub(r'\s+', ' ', node.value)))
                continue
            tag = node.tag
            if tag in SKIPPED:
                continue
            anchor = self.anchor(node)
            if tag == 'br':
                parts.append('<br>')
            elif tag in ('code', 'kbd', 'samp'):
                parts.append(anchor + self.code_span(self.plain_text(node)))
            elif tag in ('strong', 'b'):
                inner = self.inline(node.children).strip()
                parts.append(anchor + (f'**{inner}**' if inner else ''))
            elif tag in ('em', 'i'):
                inner = self.inline(node.children).strip()
                parts.append(anchor + (f'*{inner}*' if inner else ''))
            elif tag == 'a':
                parts.append(anchor + self.link(node))
            elif tag == 'img':
                alt = self.escape(node.attrs.get('alt', ''))
                parts.append(anchor + f'![{alt}]({self.target(node.attrs.get("src", ""))})')
            elif tag == 'pre':
                parts.append(anchor + self.code_span(self.plain_text(node)))
            else:
                parts.append(anchor + self.inline(node.children))
        return re.sub(r' {2,}', ' ', ''.join(parts))

    def code_span(self, value: str) -> str:
        value = re.sub(r'\s*\n\s*', ' ', value)
        if not value:
            return ''
        if self.in_table:
            value = value.replace('|', '\\|')
        run = max((len(m) for m in re.findall(r'`+', value)), default=0)
        fence = '`' * (run + 1)
        pad = ' ' if value.startswith('`') or value.endswith('`') else ''
        return f'{fence}{pad}{value}{pad}{fence}'

    def target(self, href: str) -> str:
        parts = urlsplit(href)
        if href.startswith('#') or parts.scheme or parts.netloc:
            return href if not re.search(r'[\s()]', href) else f'<{href}>'
        return urljoin(self.base_url, href) if self.base_url else ''

    def link(self, node) -> str:
        text = self.inline(node.children).strip()
        href = node.attrs.get('href', '')
        destination = self.target(href) if href else ''
        if not text:
            return f'<{destination}>' if destination and not destination.startswith('#') else ''
        return f'[{text}]({destination})' if destination else text

    # -- blocks
    def blocks(self, nodes) -> list[str]:
        out, run = [], []

        def flush():
            text = self.inline(run).strip()
            run.clear()
            if text:
                out.append(self.paragraph(text))

        for node in nodes:
            if isinstance(node, _Text) or node.tag not in BLOCKS:
                run.append(node)
            else:
                flush()
                out.extend(self.block(node))
        flush()
        return out

    @staticmethod
    def paragraph(text: str) -> str:
        if re.match(r'(#{1,6}|[-+=])(\s|$)', text):
            return '\\' + text
        return re.sub(r'^(\d+)([.)])(\s|$)', r'\1\\\2\3', text)

    def block(self, node) -> list[str]:
        tag = node.tag
        anchor = self.anchor(node)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            return ['#' * int(tag[1]) + ' ' + anchor + self.inline(node.children).strip()]
        lead = [anchor] if anchor else []
        if tag in ('p', 'summary', 'figcaption'):
            text = self.inline(node.children).strip()
            return lead + ([self.paragraph(text)] if text else [])
        if tag in ('ul', 'ol'):
            return lead + self.list(node)
        if tag == 'pre':
            return lead + [self.fence(node)]
        if tag == 'table':
            return lead + [self.table(node)]
        if tag == 'details':
            return lead + self.details(node)
        if tag == 'blockquote':
            body = '\n\n'.join(self.blocks(node.children))
            return lead + ['\n'.join('> ' + line if line else '>' for line in body.split('\n'))]
        if tag == 'dl':
            return lead + self.definitions(node)
        if tag == 'hr':
            return lead + ['---']
        return lead + self.blocks(node.children)

    @staticmethod
    def indent(marker: str, body: str) -> str:
        lines = body.split('\n') if body else ['']
        pad = ' ' * len(marker)
        return marker + lines[0] + ''.join('\n' + (pad + line if line else '') for line in lines[1:])

    def list(self, node) -> list[str]:
        ordered = node.tag == 'ol'
        try:
            number = int(node.attrs.get('start', '1'))
        except ValueError:
            number = 1
        items = []
        for child in node.children:
            if isinstance(child, _Text):
                if child.value.strip():
                    items.append(self.indent('- ', self.inline([child]).strip()))
                else:
                    self.written.add(id(child))
                continue
            if child.tag in SKIPPED:
                continue
            marker = f'{number}. ' if ordered else '- '
            number += 1
            nodes = child.children if child.tag == 'li' else [child]
            body = '\n\n'.join(self.blocks(nodes))
            items.append(self.indent(marker, (self.anchor(child) if child.tag == 'li' else '') + body))
        return ['\n'.join(items)] if items else []

    def fence(self, node) -> str:
        classes = node.attrs.get('class', '').split()
        language = 'mermaid' if 'mermaid' in classes else ''
        if not language:
            code = next((c for c in node.children if isinstance(c, _Node) and c.tag == 'code'), None)
            found = re.search(r'language-(\S+)', code.attrs.get('class', '')) if code else None
            language = found[1] if found else ''
        value = self.plain_text(node).rstrip('\n')
        run = max((len(m) for m in re.findall(r'`{3,}', value)), default=2)
        fence = '`' * (run + 1)
        return f'{fence}{language}\n{value}\n{fence}'

    def details(self, node) -> list[str]:
        summary = next((c for c in node.children if isinstance(c, _Node) and c.tag == 'summary'), None)
        rest = [c for c in node.children if c is not summary]
        head = '<details open>'
        if summary is not None:
            head += '\n<summary>' + html.escape(re.sub(r'\s+', ' ', self.plain_text(summary)).strip()) + '</summary>'
        return [head, *self.blocks(rest), '</details>']

    def definitions(self, node) -> list[str]:
        items, term = [], None
        for child in node.children:
            if isinstance(child, _Text):
                if child.value.strip():
                    items.append('- ' + self.inline([child]).strip())
                else:
                    self.written.add(id(child))
            elif child.tag == 'dt':
                if term is not None:
                    items.append(f'- **{term}**')
                term = self.inline(child.children).strip()
            elif child.tag == 'dd':
                body = '\n\n'.join(self.blocks(child.children))
                label = f'**{term}**: ' if term else ''
                items.append(self.indent('- ', label + body))
                term = None
            elif child.tag not in SKIPPED:
                items.extend(self.indent('- ', block) for block in self.blocks([child]))
        if term is not None:
            items.append(f'- **{term}**')
        return ['\n'.join(items)] if items else []

    def table(self, node) -> str:
        rows = []

        def collect(current):
            for child in current.children:
                if isinstance(child, _Node):
                    if child.tag == 'tr':
                        rows.append(child)
                    elif child.tag in ('thead', 'tbody', 'tfoot'):
                        collect(child)

        collect(node)
        cells = [[c for c in row.children if isinstance(c, _Node) and c.tag in ('th', 'td')] for row in rows]

        def structured(current):
            return any(isinstance(c, _Node) and (c.tag in _STRUCTURE or structured(c)) for c in current.children)

        if not rows or any(structured(cell) for row in cells for cell in row):
            # Markdown tables hold one line per cell; keep the original structure as HTML instead.
            return self.html(node)
        self.in_table = True
        try:
            text = [[re.sub(r'\s*\n\s*', '<br>', self.inline(cell.children).strip()) for cell in row] for row in cells]
        finally:
            self.in_table = False
        for row in rows:  # whitespace between cells
            for child in row.children:
                if isinstance(child, _Text):
                    self.written.add(id(child))
        width = max(len(row) for row in text) or 1
        text = [row + [''] * (width - len(row)) for row in text]
        lines = ['| ' + ' | '.join(text[0]) + ' |', '|' + ' --- |' * width]
        lines += ['| ' + ' | '.join(row) + ' |' for row in text[1:]]
        return '\n'.join(lines)

    def html(self, node) -> str:
        if isinstance(node, _Text):
            self.written.add(id(node))
            return html.escape(node.value, quote=False)
        if node.tag in SKIPPED:
            return ''
        attrs = dict(node.attrs)
        if node.tag == 'details':
            attrs['open'] = ''
        if node.tag in ('a', 'img'):
            key = 'href' if node.tag == 'a' else 'src'
            if key in attrs:
                destination = self.target(attrs[key])
                if destination:
                    attrs[key] = destination.strip('<>')
                else:
                    attrs.pop(key)
        opened = '<' + node.tag + ''.join(f' {k}="{html.escape(v, quote=True)}"' if v else f' {k}'
                                          for k, v in attrs.items()) + '>'
        if node.tag in VOID:
            return opened
        return opened + ''.join(self.html(child) for child in node.children) + f'</{node.tag}>'


def to_markdown(fragment: str, *, base_url: str = '') -> str:
    """Convert generated HTML to Markdown and fail if any visible text would be lost."""
    from .visual_dom import parse
    root = parse('<!doctype html><html><body>' + fragment + '</body></html>', _Node)
    body = next(_find(root, 'body'))
    referenced = {unquote(m[1]) for m in re.finditer(r'href="#([^"]+)"', fragment)}
    converter = _Markdown(referenced, base_url)
    markdown = '\n\n'.join(block for block in converter.blocks(body.children) if block.strip()) + '\n'
    missing = [text.value.strip() for text in _text_nodes(body)
               if text.value.strip() and id(text) not in converter.written]
    if missing:
        raise RuntimeError('Whole document Markdown would omit text: ' + ' | '.join(m[:80] for m in missing[:5]))
    return re.sub(r'\n{3,}', '\n\n', markdown)


def _find(node, tag):
    if isinstance(node, _Node):
        if node.tag == tag:
            yield node
        for child in node.children:
            yield from _find(child, tag)
