"""Assemble the reader edition from validated, localized source pages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from xml.dom import Node

import html5lib

from .site_fragments import fragment_id
from .site_markdown import _href, _html_path
from .site_paths import owned_path
from .validation_stage import load_yaml, read_bytes

REPORT = 'reader-edition.json'
ARCHIVE = 'reader-archive/'
COMPATIBILITY_ASSET = Path(__file__).parent / 'reader_assets' / 'reader-compatibility.js'
HEADINGS = {f'h{i}': i for i in range(2, 7)}
HTML_OPTIONS = dict(quote_attr_values='always', omit_optional_tags=False,
                    use_trailing_solidus=False, minimize_boolean_attributes=False)


def _require(condition, message):
    if not condition:
        raise ValueError('Reader edition: ' + message)


def _label(value):
    return isinstance(value, str) and bool(value.strip())


def _route(value):
    return (isinstance(value, str) and bool(re.fullmatch(r'[a-z0-9][a-z0-9_/-]*\.md', value))
            and not value.startswith(('en/', 'assets/', 'download/', ARCHIVE))
            and PurePosixPath(value).as_posix() == value)


def _translated(value):
    return isinstance(value, dict) and set(value) == {'ko', 'en'} and all(map(_label, value.values()))


@dataclass(frozen=True)
class Edition:
    groups: dict
    pages: list
    aliases: dict

    @property
    def entries(self):
        return [(self.groups[page['group']]['ko'], page['ko'], page['path']) for page in self.pages]


def load(cfg):
    path = cfg.site.reader_edition
    if not path:
        return None
    _require(isinstance(path, str), 'site.reader_edition must name a YAML file')
    data = load_yaml(owned_path(cfg.root, path))
    _require(isinstance(data, dict) and data.get('schema') == 1
             and not set(data) - {'schema', 'groups', 'pages', 'aliases'},
             'expected schema 1 with groups, pages and optional aliases')
    _require(isinstance(data.get('groups'), list) and data['groups'], 'groups must be a nonempty list')
    groups = {}
    for group in data['groups']:
        _require(isinstance(group, dict) and set(group) == {'id', 'ko', 'en'}
                 and all(map(_label, group.values())), 'each group needs id, ko and en')
        _require(group['id'] not in groups, 'duplicate group ' + group['id'])
        groups[group['id']] = {'ko': group['ko'], 'en': group['en']}
    pages = data.get('pages')
    _require(isinstance(pages, list) and pages, 'pages must be a nonempty list')
    paths = set()
    for page in pages:
        _require(isinstance(page, dict) and not set(page) - {
            'path', 'group', 'ko', 'en', 'intro', 'links', 'sections', 'table', 'table_source'},
            'unknown page field')
        name = page.get('path')
        _require(_route(name) and name not in paths, f'invalid or duplicate page path {name!r}')
        paths.add(name)
        _require(_label(page.get('group')) and page['group'] in groups
                 and _label(page.get('ko')) and _label(page.get('en')), 'page needs group, ko and en')
        if 'intro' in page:
            _require(_translated(page['intro']), 'intro needs ko and en for ' + name)
        if 'table' in page:
            table = page['table']
            _require(isinstance(table, dict) and set(table) == {'ko', 'en'}, 'table needs ko and en for ' + name)
            for rows in table.values():
                _require(isinstance(rows, list) and len(rows) >= 2 and isinstance(rows[0], list) and rows[0]
                         and all(isinstance(row, list) and len(row) == len(rows[0]) and all(map(_label, row))
                                 for row in rows), 'table rows must have equal column counts and text in ' + name)
            _require(len(table['ko']) == len(table['en']) and len(table['ko'][0]) == len(table['en'][0]),
                     'table shapes differ between languages in ' + name)
            binding = page.get('table_source')
            _require(isinstance(binding, dict) and set(binding) == {'source', 'fragment', 'sha256'}
                     and _route(binding['source']) and _label(binding['fragment'])
                     and isinstance(binding['sha256'], dict) and set(binding['sha256']) == {'ko', 'en'}
                     and all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                             for value in binding['sha256'].values()), 'table needs a bilingual source digest in ' + name)
        else:
            _require('table_source' not in page, 'table_source requires a table in ' + name)
        _require(isinstance(page.get('sections'), list) and page['sections'],
                 'page needs sections for ' + name)
        for part in page['sections']:
            _require(isinstance(part, dict) and not set(part) - {'source', 'fragment', 'id', 'ko', 'en', 'children'}
                     and _route(part.get('source')), 'invalid section source in ' + name)
            for key in ('fragment', 'id'):
                if key in part:
                    _require(_label(part[key]) and not re.search(r'[\s#]', part[key]),
                             f'invalid {key} in {name}')
            if 'ko' in part or 'en' in part:
                _require(_label(part.get('ko')) and _label(part.get('en')),
                         'section heading override needs ko and en in ' + name)
            if 'children' in part:
                children = part['children']
                _require(part.get('fragment') not in (None, '@intro') and isinstance(children, list)
                         and all(_label(child) and not re.search(r'[\s#]', child) for child in children)
                         and len(children) == len(set(children)), 'children need distinct IDs under a section in ' + name)
        if 'table_source' in page:
            binding = page['table_source']
            _require(any(part.get('source') == binding['source'] and part.get('fragment') == binding['fragment']
                         for part in page['sections']), 'table source must appear on the same page in ' + name)
        _require(isinstance(page.get('links', []), list), 'links must be a list in ' + name)
    _require(pages[0]['path'] == 'index.md', 'first page must be index.md')
    group_order = list(dict.fromkeys(page['group'] for page in pages))
    _require(group_order == list(groups) and [page['group'] for page in pages]
             == sorted((page['group'] for page in pages), key=group_order.index),
             'each group must appear in configuration order and have consecutive pages')
    for page in pages:
        for link in page.get('links', []):
            _require(isinstance(link, dict) and set(link) == {'path', 'ko', 'en'}
                     and all(map(_label, link.values())) and link['path'].split('#')[0] in paths,
                     'invalid reader link in ' + page['path'])
    aliases = data.get('aliases', {})
    _require(isinstance(aliases, dict) and all(_route(key) and _label(value)
             and value.split('#')[0] in paths for key, value in aliases.items()), 'invalid aliases')
    return Edition(groups, pages, aliases)


def _elements(node):
    if node.nodeType == Node.ELEMENT_NODE:
        yield node
    for child in node.childNodes:
        yield from _elements(child)


def _ids(node):
    return {element.getAttribute('id') for element in _elements(node) if element.hasAttribute('id')}


def _parse(source):
    return html5lib.parse(source, treebuilder='dom', namespaceHTMLElements=False)


def _fragment():
    return html5lib.parseFragment('', treebuilder='dom', namespaceHTMLElements=False)


def _render(node):
    return html5lib.serialize(node, tree='dom', **HTML_OPTIONS)


def _of_class(node, name):
    return name in node.getAttribute('class').split()


def _first(node, *, tag=None, cls=None, identifier=None):
    return next((element for element in _elements(node) if (tag is None or element.tagName == tag)
                 and (cls is None or _of_class(element, cls))
                 and (identifier is None or element.getAttribute('id') == identifier)), None)


def _text(node):
    if node.nodeType == Node.TEXT_NODE:
        return node.data
    return ''.join(map(_text, node.childNodes))


def _set_text(node, label):
    while node.firstChild:
        node.removeChild(node.firstChild)
    node.appendChild(node.ownerDocument.createTextNode(label))


def _section(article, part):
    fragment = part.get('fragment')
    if fragment is None:
        return list(article.childNodes)
    if fragment == '@intro':
        return _following(article.firstChild, 7, introductory=True)
    heading = _first(article, identifier=fragment)
    _require(heading is not None and heading.tagName in HEADINGS,
             f'{part["source"]} has no heading #{fragment}')
    level = HEADINGS[heading.tagName]
    nodes = _following(heading, level)
    if 'children' not in part:
        return nodes
    expected = set(part['children'])
    found = set()
    child_ranges = []
    for item in nodes:
        if item.nodeType == Node.ELEMENT_NODE and HEADINGS.get(item.tagName) == level + 1:
            anchor = item.getAttribute('id')
            found.add(anchor)
            child_ranges.append((nodes.index(_heading_start(item)), anchor))
    _require(expected <= found, f'{part["source"]}#{fragment} is missing one or more configured child headings')
    selected = nodes[:child_ranges[0][0]] if child_ranges else nodes
    for (start, anchor), (end, _) in zip(child_ranges, child_ranges[1:] + [(len(nodes), '')]):
        if anchor in expected:
            selected.extend(nodes[start:end])
    return selected


def _heading_start(heading):
    """An opening diagram marker immediately before a heading owns that heading."""
    first = heading
    previous = heading.previousSibling
    while previous is not None:
        if previous.nodeType == Node.TEXT_NODE and not previous.data.strip():
            previous = previous.previousSibling
        elif previous.nodeType == Node.COMMENT_NODE and re.fullmatch(
            r'sdd:(?:class-diagram|visual:[a-z][a-z0-9_-]*)', previous.data.strip()
        ):
            first = previous
            previous = previous.previousSibling
        else:
            break
    return first


def _following(current, level, introductory=False):
    first_heading = None if introductory else current
    if first_heading is not None:
        current = _heading_start(first_heading)
    nodes = []
    while current is not None:
        if (current is not first_heading and current.nodeType == Node.ELEMENT_NODE
                and HEADINGS.get(current.tagName, 8) <= level):
            next_start = _heading_start(current)
            if next_start in nodes:
                del nodes[nodes.index(next_start):]
            break
        nodes.append(current)
        current = current.nextSibling
    return nodes


def _selected(prefix, edition, trees):
    origins = {}
    selections = {}
    # Reserve template anchors, which belong to the page shell rather than source sections.
    shell = {'main', 'page-evidence', 'sidebar', 'site-config', 'search-open', 'menu-toggle'}
    for page in edition.pages:
        target = prefix + _html_path(page['path'])
        taken = set(shell)
        parts = []
        for part in page['sections']:
            source = prefix + _html_path(part['source'])
            _require(source in trees, 'source page is not in the rendered inventory: ' + source)
            tree = trees[source]
            article = _first(tree, tag='article')
            _require(article is not None, 'source article missing: ' + source)
            fragment = _fragment()
            for node in _section(article, part):
                fragment.appendChild(node.cloneNode(deep=True))
            _require(any(_text(node).strip() for node in fragment.childNodes),
                     'source selection is empty: ' + source + '#' + part.get('fragment', ''))
            binding = page.get('table_source', {})
            if part.get('source') == binding.get('source') and part.get('fragment') == binding.get('fragment'):
                language = 'en' if prefix else 'ko'
                actual = section_digest(fragment)
                _require(actual == binding['sha256'][language],
                         f'{language} table evidence changed: {source}#{part["fragment"]}; actual sha256 {actual}')
            selected_id = part.get('fragment')
            heading = _first(fragment, identifier=selected_id) if selected_id not in (None, '@intro') else None
            synthetic = None
            if heading is None and any(key in part for key in ('ko', 'en', 'id')):
                heading = fragment.ownerDocument.createElement('h2')
                synthetic = heading
                fragment.insertBefore(heading, fragment.firstChild)
                _set_text(heading, part.get('en' if prefix else 'ko') or _text(_first(tree, tag='h1')))
                heading.setAttribute('id', part.get('id') or PurePosixPath(part['source']).stem)
            if heading is not None:
                if 'ko' in part:
                    _set_text(heading, part['en' if prefix else 'ko'])
                # Reparent a subsection to the reader page without changing the relative depth of its children.
                level = HEADINGS[heading.tagName]
                if level > 2:
                    for element in _elements(fragment):
                        if element.tagName in HEADINGS:
                            element.tagName = element.nodeName = 'h' + str(max(2, HEADINGS[element.tagName] - level + 2))
            local = {}
            for element in _elements(fragment):
                if not element.hasAttribute('id'):
                    continue
                old = element.getAttribute('id')
                requested = part['id'] if element is heading and 'id' in part else old
                destination = requested
                number = 1
                while destination in taken:
                    _require(element is not heading or 'id' not in part,
                             f'duplicate explicit reader ID {requested!r} in {target}')
                    number += 1
                    destination = f'{requested}-{number}'
                taken.add(destination)
                element.setAttribute('id', destination)
                if element is synthetic:
                    continue
                _require(old not in local, f'ambiguous source fragment {source}#{old}')
                local[old] = destination
                origin = (source, old)
                _require(origin not in origins, f'source fragment selected more than once: {source}#{old}')
                origins[origin] = (target, destination)
            for element in _elements(fragment):
                for attr in ('for', 'aria-controls', 'aria-labelledby', 'aria-describedby'):
                    if element.hasAttribute(attr):
                        element.setAttribute(attr, ' '.join(local.get(value, value)
                                             for value in element.getAttribute(attr).split()))
            parts.append((part, source, fragment, local))
        selections[target] = parts
    return selections, origins


def section_digest(fragment):
    def visible(node):
        if node.nodeType == Node.TEXT_NODE:
            return node.data
        if node.nodeType == Node.ELEMENT_NODE and set(node.getAttribute('class').split()) & {
            'citation', 'evidence', 'evidence-links', 'source-excerpts', 'mermaid'
        }:
            return ''
        return ' '.join(map(visible, node.childNodes))
    return hashlib.sha256(' '.join(visible(fragment).split()).encode()).hexdigest()


def _link(rel, target, fragment=''):
    return ('' if fragment and rel == target else _href(target, rel)) + ('#' + quote(fragment) if fragment else '')


def _relocate(value, source, current, routes, legacy, ids):
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or value.startswith('/') or not (parts.path or parts.fragment):
        return value
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parts.path))) if parts.path else source
    fragment = parts.fragment
    anchor = fragment_id(fragment, ids.get(target, ())) if fragment else ''
    if (target, anchor) in routes:
        target, fragment = routes[target, anchor]
        fragment = quote(fragment)
    elif target in legacy:
        target = legacy[target]
    path = _href(target, current) if target != current or not fragment else ''
    return urlunsplit(('', '', path, parts.query, fragment))


def _rewrite(node, source, current, routes, legacy, ids):
    def relocate(value):
        return _relocate(value, source, current, routes, legacy, ids)
    for element in _elements(node):
        for attr in ('href', 'src', 'poster'):
            if element.hasAttribute(attr):
                element.setAttribute(attr, relocate(element.getAttribute(attr)))
        if element.hasAttribute('data-sdd-excerpts'):
            excerpts = json.loads(element.getAttribute('data-sdd-excerpts'))
            rewritten = {cite: [relocate(value) for value in links] for cite, links in excerpts.items()}
            element.setAttribute('data-sdd-excerpts', json.dumps(rewritten, ensure_ascii=False))
        if element.hasAttribute('data-sdd-evidence'):
            evidence = json.loads(element.getAttribute('data-sdd-evidence'))
            rewritten = [[cite, re.sub(r'href="([^"]+)"', lambda match: 'href="' + html.escape(
                relocate(html.unescape(match[1])), quote=True) + '"', markup)] for cite, markup in evidence]
            element.setAttribute('data-sdd-evidence', json.dumps(rewritten, ensure_ascii=False))


def _toc(parts):
    root = []
    parents = [(1, root)]
    for _, _, fragment, _ in parts:
        for element in _elements(fragment):
            if element.tagName not in HEADINGS or not element.hasAttribute('id'):
                continue
            level = HEADINGS[element.tagName]
            while parents[-1][0] >= level:
                parents.pop()
            children = []
            parents[-1][1].append((element.getAttribute('id'), _text(element), children))
            parents.append((level, children))
    def render(items):
        return '<ul>' + ''.join('<li><a href="#' + quote(anchor) + '">' + html.escape(label) + '</a>'
                                + (render(children) if children else '') + '</li>'
                                for anchor, label, children in items) + '</ul>'
    return '<div class="toc">' + render(root) + '</div>'


def _navigation(edition, prefix, language, current):
    groups = []
    for group, labels in edition.groups.items():
        key = hashlib.sha256(group.encode()).hexdigest()[:24]
        links = []
        for page in edition.pages:
            if page['group'] == group:
                target = prefix + _html_path(page['path'])
                active = ' aria-current="page"' if current == target else ''
                links.append(f'<a href="{_link(current, target)}"{active}>{html.escape(page[language])}</a>')
        groups.append(f'<details class="nav-group" data-nav-id="group-{key}" open>'
                      f'<summary>{html.escape(labels[language])}</summary>{"".join(links)}</details>')
    return ''.join(groups)


def _part(pattern, source, label):
    matches = list(re.finditer(pattern, source, re.S))
    _require(len(matches) == 1, f'expected one {label} in rendered source')
    return matches[0]


def _replace(pattern, source, replacement, label):
    found = _part(pattern, source, label)
    return source[:found.start()] + replacement + source[found.end():]


def _shell(raw, source, current, prefix, edition, language, *, archived=False):
    # The ordinary renderer still owns its header, asset cache keys and UI localization.
    from .site_localization import selector

    def move(match):
        name, url = match.groups()
        value = html.unescape(url)
        if value.startswith('#'):
            return match[0]
        return f'{name}="{html.escape(_relocate(value, source, current, {}, {}, {}), quote=True)}"'

    document = re.sub(r'(href|src)="([^"]+)"', move, raw)
    document = re.sub(r'<details class="language-selector">.*?</details>', '', document, count=1, flags=re.S)
    document = re.sub(r'<link rel="alternate"[^>]*>', '', document)
    document = re.sub(r'(?<=class="brand" )href="[^"]+"',
                      lambda _: 'href="' + _href(prefix + 'index.html', current) + '"', document)
    menu = _part(r'(<aside id="sidebar">.*?)<nav aria-label="([^"]+)">.*?</nav>', document, 'sidebar menu')
    navigation = _navigation(edition, prefix, language, current) if not archived else ''
    document = document[:menu.start()] + menu[1] + '<nav aria-label="' + menu[2] + '">' + (
        navigation) + '</nav>' + document[menu.end():]
    config = _part(r'<script id="site-config" type="application/json">(.+?)</script>', document,
                   'site config')
    settings = json.loads(config[1])
    settings['root'] = _href(prefix + 'index.html', current).removesuffix('index.html') or './'
    if not archived:
        settings.pop('index', None)
    encoded = json.dumps(settings, ensure_ascii=False).replace('<', '\\u003c')
    document = document[:config.start(1)] + encoded + document[config.end(1):]
    if archived:
        document = document.replace('</head>', '<meta name="robots" content="noindex"></head>', 1)
    if prefix or '<html lang="ko">' in raw:
        relative = current.removeprefix(prefix)
        document = selector(document, relative, bool(prefix))
    return document


def _links(page, current, prefix, lang):
    links = []
    for link in page.get('links', []):
        path, _, anchor = link['path'].partition('#')
        item = ('<a href="' + _link(current, prefix + _html_path(path), anchor) + '">'
                + html.escape(link[lang]) + '</a>')
        links.append(('<section>' + item + '</section>') if page['path'] == 'index.md'
                     else '<li>' + item + '</li>')
    if links and page['path'] == 'index.md':
        return '<div class="reader-start">' + ''.join(links) + '</div>'
    return '<ul class="reader-edition-links">' + ''.join(links) + '</ul>' if links else ''


def _table(page, lang):
    if 'table' not in page:
        return ''
    columns, *rows = page['table'][lang]
    headings = ''.join(f'<th scope="col">{html.escape(value)}</th>' for value in columns)
    body = ''.join('<tr>' + ''.join(f'<td data-label="{html.escape(col, quote=True)}">{html.escape(value)}</td>'
                 for col, value in zip(columns, row, strict=True)) + '</tr>' for row in rows)
    label = 'Table' if lang == 'en' else '표'
    return (f'<div class="table-scroll stack" tabindex="0" role="region" aria-label="{label}"><table>'
            '<thead><tr>' + headings + '</tr></thead><tbody>' + body + '</tbody></table></div>')


def _pagination(edition, page, current, prefix, language):
    following = []
    index = edition.pages.index(page)
    for offset, css, label, arrow in ((-1, 'previous', 'Previous' if prefix else '이전', '←'),
                                       (1, 'next', 'Next' if prefix else '다음', '→')):
        if 0 <= index + offset < len(edition.pages):
            target = edition.pages[index + offset]
            following.append(f'<a class="{css}" href="{_link(current, prefix + _html_path(target["path"]))}">'
                             f'<small>{label}</small>{html.escape(target[language])} {arrow}</a>')
    return ''.join(following)


def _canonical(out, edition, page, parts, raw, trees, prefix, routes, legacy, old_ids):
    current = prefix + _html_path(page['path'])
    language = 'en' if prefix else 'ko'
    template = prefix + 'index.html'
    document = _shell(raw[template], template, current, prefix, edition, language)
    heading = html.escape(page[language])
    group = html.escape(edition.groups[page['group']][language])
    table_title = 'On this page' if prefix else '이 페이지에서'
    original_title = _part(r'<title>.*?( · .*?)</title>', document, 'title')
    document = document[:original_title.start()] + '<title>' + heading + original_title[1] + '</title>' + document[original_title.end():]
    intro = '<p>' + html.escape(page['intro'][language]) + '</p>' if 'intro' in page else ''
    toc = _toc(parts)
    content = []
    provenance = []
    reserved = {'page-evidence', 'main'} | {item for _, _, fragment, _ in parts for item in _ids(fragment)}
    for part, source, fragment, mapping in parts:
        _rewrite(fragment, source, current, routes, legacy, old_ids)
        content.append(_render(fragment))
        provenance.append({'source': source, 'fragment': part.get('fragment'),
                           'anchors': mapping})
    note = ('<p class="translation-note">English translation · human review pending. '
            'Review states below refer to the Korean source.</p>') if prefix else ''
    pagination = _pagination(edition, page, current, prefix, language)
    old_main = _part(r'<main id="main".*?</main>', document, 'main')
    reserved.update(_ids(_parse(document[:old_main.start()] + document[old_main.end():])))
    old_footer = _part(r'<footer>.*?</footer>', old_main[0], 'footer')
    evidence = _evidence(trees, parts, current, prefix, legacy, old_ids)
    compatibility, redirect = _overlapping_fragments(current, prefix, routes, legacy, old_ids, reserved)
    lead = intro + _links(page, current, prefix, language)
    article = lead + _table(page, language) + ''.join(content)
    markdown_target = prefix + page['path']
    download = ('Download page Markdown' if prefix else '이 페이지 Markdown 받기')
    inventory = 'Reader edition source map' if prefix else '독자용 문서의 원본 위치'
    evidence += (f'<p><a href="{_link(current, markdown_target)}" download>{download}</a> · '
                 f'<a href="{_link(current, REPORT)}">{inventory}</a></p>')
    nav_label = 'Previous and next pages' if prefix else '이전과 다음 문서'
    mobile_toc = f'<details class="mobile-toc"><summary>{table_title}</summary>{toc}</details>'
    if page['path'] == 'index.md':
        lead_toc = f'<nav aria-label="{table_title}">{mobile_toc}</nav>'
        article_html = lead + lead_toc + _table(page, language) + ''.join(content)
        mobile_toc = ''
    else:
        article_html = article
    main = (f'<main id="main"><p class="breadcrumb">{group} <span>/</span> {heading}</p>'
            f'<h1>{heading}</h1>{mobile_toc}{note}<article>{article_html}</article>{evidence}'
            f'<nav class="pagination" aria-label="{nav_label}">{pagination}</nav>{compatibility}{old_footer[0]}</main>')
    document = document[:old_main.start()] + main + document[old_main.end():]
    if redirect:
        document = document.replace('</body>', redirect + '</body>', 1)
    document = _replace(r'<aside class="page-toc">.*?</aside>', document,
                        f'<aside class="page-toc"><nav aria-label="{table_title}"><p>{table_title}</p>{toc}</nav></aside>',
                        'desktop table of contents')
    from .full_document import to_markdown
    destination = owned_path(out, markdown_target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(to_markdown(f'<h1>{heading}</h1>{article}{evidence}'), encoding='utf-8', newline='\n')
    return document, provenance


def _evidence(trees, parts, current, prefix, legacy, old_ids):
    label = 'Source manuscripts and review records' if prefix else '원고와 검토 기록'
    moved = 'Open earlier detail' if prefix else '이전 주소의 상세 내용 열기'
    links = []
    for source in dict.fromkeys(source for _, source, _, _ in parts):
        document = trees[source]
        title = html.escape(_text(_first(document, tag='h1')))
        previous = legacy[source]
        # The source's own record stays visible with its commit, checks, approvals and download links.
        record = _first(document, cls='evidence', identifier=None)
        if record is not None:
            record = record.cloneNode(deep=True)
            _rewrite(record, source, current, {}, legacy, old_ids)
            record.removeAttribute('class')
            # The source evidence heading becomes the disclosure summary. Retain any other
            # source IDs only on their original address to avoid collisions across records.
            original_heading = _first(record, tag='h2')
            if original_heading:
                original_heading.parentNode.removeChild(original_heading)
            for item in _elements(record):
                if item.hasAttribute('id'):
                    item.removeAttribute('id')
            content = _render(record)
        else:
            content = ''
        href = _link(current, previous, 'page-evidence' if 'page-evidence' in old_ids[source] else '')
        links.append(f'<details><summary>{title}</summary>{content}<p><a href="{href}">{moved}</a></p></details>')
    return f'<section class="evidence"><h2 id="page-evidence">{label}</h2>' + ''.join(links) + '</section>'


def _overlapping_fragments(current, prefix, routes, legacy, old_ids, reserved):
    if current not in legacy:
        return '', ''
    moved = 'Open earlier detail' if prefix else '이전 주소의 상세 내용 열기'
    links = []
    destinations = {}
    for anchor in sorted(old_ids[current] - reserved):
        target, identifier = routes.get((current, anchor), (legacy[current], anchor))
        href = _link(current, target, identifier)
        destinations[anchor] = href
        links.append(f'<li id="{html.escape(anchor, quote=True)}"><a href="'
                     f'{href}">{html.escape(anchor)}</a></li>')
    if not links:
        return '', ''
    return (f'<details class="reader-old-fragments"><summary>{moved}</summary><ul>'
            + ''.join(links) + '</ul></details>', _compatibility_data(current, destinations))


def _archive(edition, raw, source, destination, prefix, routes, legacy, old_ids, projected):
    language = 'en' if prefix else 'ko'
    document = _shell(raw[source], source, destination, prefix, edition, language, archived=True)
    old_main = _part(r'<main id="main".*?</main>', document, 'archive main')
    tree = _parse(_part(r'<main id="main".*?</main>', raw[source], 'original main')[0])
    main = _first(tree, identifier='main')
    article = _first(main, tag='article')
    for item in list(_elements(main)):
        if _of_class(item, 'mobile-toc'):
            item.parentNode.removeChild(item)
    archive_sections = [(part, _section(article, part)) for part in projected]
    _rewrite(main, source, destination, routes, legacy, old_ids)
    for part, selection in archive_sections:
        _trim_selection(selection, source, destination, routes, language)
    back = routes.get((source, ''), (prefix + 'index.html', ''))
    text = 'Reader edition' if prefix else '독자용 문서로 이동'
    archive_note = 'Source material linked by earlier addresses' if prefix else '이전 주소에서 연결하는 원본 자료'
    notice = (f'<p class="translation-note">{archive_note} · <a href="'
              f'{_link(destination, *back)}">{text}</a></p>')
    doc = _render(main).replace('<article>', notice + '<article>', 1)
    document = document[:old_main.start()] + doc + document[old_main.end():]
    return _replace(r'<aside class="page-toc">.*?</aside>', document, '<aside class="page-toc"></aside>',
                    'archive table of contents')


def _trim_selection(selection, source, destination, routes, language):
    """Leave links and exact source-excerpt panels where duplicated prose was removed."""
    for item in selection:
        parent = item.parentNode
        if parent is None:
            continue
        elements = list(_elements(item))
        excerpts = set()
        for element in elements:
            if _of_class(element, 'source-excerpts') and not any(element in list(_elements(old)) for old in excerpts):
                excerpts.add(element)
        kept = {element for excerpt in excerpts for element in _elements(excerpt)}
        for element in elements:
            if element in excerpts:
                if element is not item:
                    parent.insertBefore(element, item)
                continue
            if element in kept or not element.hasAttribute('id'):
                continue
            anchor = element.getAttribute('id')
            target = routes.get((source, anchor))
            if target is None:
                continue
            marker = item.ownerDocument.createElement('p')
            marker.setAttribute('id', anchor)
            link = item.ownerDocument.createElement('a')
            link.setAttribute('href', _link(destination, *target))
            label = 'Open this section in the reader edition' if language == 'en' else '독자용 문서에서 이 내용 열기'
            if element.tagName in HEADINGS:
                label = ' '.join(_text(element).split()) or label
            _set_text(link, label)
            marker.appendChild(link)
            parent.insertBefore(marker, item)
        if item not in excerpts:
            parent.removeChild(item)


def _compatibility(source, archive, prefix, routes, anchors):
    lang = 'en' if prefix else 'ko'
    title = 'Earlier document address' if prefix else '이전 문서 주소'
    orientation = 'Open the reader edition' if prefix else '독자용 문서 열기'
    details = 'Open the archived document' if prefix else '이전 문서 원본 열기'
    primary = _link(source, *routes.get((source, ''), (prefix + 'index.html', '')))
    content = []
    destinations = {}
    for anchor in sorted(anchors):
        target = _link(source, *routes.get((source, anchor), (archive, anchor)))
        destinations[anchor] = target
        content.append(f'<li id="{html.escape(anchor, quote=True)}"><a href="{target}">'
                       f'{html.escape(anchor)}</a></li>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head><body>'
            f'<h1>{title}</h1><p><a href="{primary}">{orientation}</a></p>'
            f'<p><a href="{_link(source, archive)}">{details}</a></p><ul>{"".join(content)}</ul>'
            + _compatibility_data(source, destinations, primary) + '</body></html>')


def _compatibility_data(current, destinations, primary=None):
    encoded = json.dumps({'page': primary, 'fragments': destinations}, ensure_ascii=False).replace('<', '\\u003c')
    assets = _href('assets/reader-compatibility.js', current)
    return (f'<script type="application/json" data-reader-compatibility>{encoded}</script>'
            f'<script defer src="{assets}"></script>')


def _write_html(out, documents):
    for name, document in documents.items():
        target = owned_path(out, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding='utf-8', newline='\n')


def _search(out, edition, selections, prefix, routes, archives, old_ids):
    location = out / prefix / 'assets' / 'search.json'
    previous = json.loads(location.read_text(encoding='utf-8'))
    lang = 'en' if prefix else 'ko'
    titles = {prefix + _html_path(page['path']): page[lang] for page in edition.pages}
    values = [{'title': title, 'page': title, 'url': current.removeprefix(prefix)}
              for current, title in titles.items()]
    for current, parts in selections.items():
        for _, _, fragment, _ in parts:
            for element in _elements(fragment):
                if element.tagName in HEADINGS and element.hasAttribute('id'):
                    values.append({'title': _text(element), 'page': titles[current],
                                   'url': current.removeprefix(prefix) + '#' + quote(element.getAttribute('id'))})
    for row in previous:
        if row.get('kind') != 'symbol' and not row['url'].startswith('glossary.html#'):
            continue
        rel, _, anchor = row['url'].partition('#')
        source = prefix + unquote(rel)
        identifier = fragment_id(anchor, old_ids.get(source, ()))
        route = routes.get((source, identifier))
        if route:
            current, identifier = route
            values.append({**row, 'page': titles[current],
                           'url': current.removeprefix(prefix) + '#' + quote(identifier)})
        elif row.get('kind') == 'symbol' and source in archives and identifier in old_ids[source]:
            context, _ = routes.get((source, ''), (prefix + 'index.html', ''))
            values.append({**row, 'page': titles[context],
                           'url': archives[source].removeprefix(prefix) + '#' + quote(identifier)})
    location.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8', newline='\n')


def _edition(out, edition, prefix, raw, *, bilingual):
    trees = {rel: _parse(text) for rel, text in raw.items()}
    old_ids = {rel: _ids(tree) for rel, tree in trees.items()}
    selections, origins = _selected(prefix, edition, trees)
    selected = set(selections)
    archives = {rel: prefix + ARCHIVE + rel.removeprefix(prefix) for rel in raw}
    routes = dict(origins)
    canonical_for = {}
    projected = {source: [] for source in raw}
    for canonical, selections_on_page in selections.items():
        for part, source, _, _ in selections_on_page:
            canonical_for.setdefault(source, canonical)
            projected[source].append(part)
    for source in raw:
        if source.removeprefix(prefix).removesuffix('.html') + '.md' in edition.aliases:
            source_key = source.removeprefix(prefix).removesuffix('.html') + '.md'
            path, _, anchor = edition.aliases[source_key].partition('#')
            routes[source, ''] = (prefix + _html_path(path), anchor)
        elif source in canonical_for:
            routes[source, ''] = (canonical_for[source], '')
    for source_key in edition.aliases:
        _require(prefix + _html_path(source_key) in raw, 'unknown alias source: ' + source_key)
    # Preserve original downloads even if a new canonical Markdown path reuses the same name.
    markdown_redirects = {}
    for page in edition.pages:
        rel = prefix + page['path']
        original = out / rel
        if original.is_file():
            archive = prefix + ARCHIVE + page['path']
            target = owned_path(out, archive)
            target.parent.mkdir(parents=True, exist_ok=True)
            original.rename(target)
            markdown_redirects[rel] = archive
    relocation = {**archives, **markdown_redirects}
    report = {}
    documents = {}
    for source, destination in archives.items():
        documents[destination] = _archive(edition, raw, source, destination, prefix, routes, relocation, old_ids,
                                          projected[source])
        if source not in selected:
            documents[source] = _compatibility(source, destination, prefix, routes, old_ids[source])
    for page in edition.pages:
        current = prefix + _html_path(page['path'])
        documents[current], report[current] = _canonical(out, edition, page, selections[current], raw, trees, prefix,
                                                          routes, relocation, old_ids)
    if not bilingual:
        # No English artifacts or alternate links are created for a monolingual source build.
        documents = {key: re.sub(r'<details class="language-selector">.*?</details>|<link rel="alternate"[^>]*>',
                                 '', value, flags=re.S) for key, value in documents.items()}
    _write_html(out, documents)
    _search(out, edition, selections, prefix, routes, archives, old_ids)
    return report, archives, origins


def publish(cfg, out):
    edition = load(cfg)
    if edition is None:
        return None
    (out / 'assets' / COMPATIBILITY_ASSET.name).write_bytes(read_bytes(COMPATIBILITY_ASSET))
    original = {file.relative_to(out).as_posix(): file.read_text(encoding='utf-8')
                for file in sorted(out.rglob('*.html'))}
    korean = {rel: document for rel, document in original.items() if not rel.startswith('en/')}
    english = {rel: document for rel, document in original.items() if rel.startswith('en/')}
    recordings, archives, origins = _edition(out, edition, '', korean, bilingual=bool(english))
    if english:
        localized, translated_archives, localized_origins = _edition(out, edition, 'en/', english, bilingual=True)
        _require({(source.removeprefix('en/'), anchor): (page.removeprefix('en/'), dest)
                  for (source, anchor), (page, dest) in localized_origins.items()} == origins,
                  'Korean and English source fragments differ')
        recordings.update(localized)
        archives.update(translated_archives)
    report = {'schema': 1, 'pages': recordings, 'archives': archives,
              'compatibility': sorted(set(archives) - set(recordings))}
    (out / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8', newline='\n')
    return edition.entries


def read_inventory(out, files):
    report = json.loads((out / REPORT).read_bytes())
    _require(isinstance(report, dict) and set(report) == {'schema', 'pages', 'archives', 'compatibility'}
             and report.get('schema') == 1 and isinstance(report['pages'], dict)
             and isinstance(report['archives'], dict) and isinstance(report['compatibility'], list),
             'invalid published reader inventory')
    canonical = set(report['pages'])
    archives = set(report['archives'].values())
    compatibility = set(report['compatibility'])
    _require(not (canonical & (archives | compatibility) or archives & compatibility)
             and canonical | archives | compatibility == set(files)
             and compatibility == set(report['archives']) - canonical,
             'published reader inventory differs from site pages')
    return report


def verify(out, pages):
    report = read_inventory(out, pages)
    archives = report['archives']
    for destination, sections in report['pages'].items():
        anchors = pages[destination].ids
        for section in sections:
            source = section['source']
            original = pages[archives[source]].ids
            _require(set(section['anchors']) <= original and set(section['anchors'].values()) <= anchors,
                     'published provenance contains a missing old or new anchor: ' + destination)
    for source, archive in archives.items():
        _require(pages[archive].ids <= pages[source].ids,
                 'older fragment URLs lost their targets: ' + source)
    for prefix in ('', 'en/'):
        canonical = {page.removeprefix(prefix) for page in report['pages'] if page.startswith(prefix)
                     and (prefix or not page.startswith('en/'))}
        if not canonical:
            continue
        search = json.loads((out / prefix / 'assets' / 'search.json').read_bytes())
        seen = set()
        for item in search:
            name, _, anchor = item['url'].partition('#')
            supported_symbol = item.get('kind') == 'symbol' and anchor and prefix + name in archives.values()
            _require((name in canonical or supported_symbol)
                     and (not anchor or fragment_id(anchor, pages[prefix + name].ids) in pages[prefix + name].ids),
                     'search target is outside reader edition: ' + item['url'])
            if not anchor:
                seen.add(name)
        _require(seen == canonical, 'search does not cover every reader page')
