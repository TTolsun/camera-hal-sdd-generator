"""Per-item visualization inventory and an opt-in, fail-closed publication gate.

Candidate heuristics never grant acceptance. A review binds the explanation,
heading ancestry, descendant items, local figures and source windows. This is
an editorial/automated review record, not human approval or runtime evidence.
"""
from __future__ import annotations

import argparse
import gzip
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit

from .validation_stage import load_json, read_bytes
from .site_paths import owned_path

STATUSES = ('appropriate', 'needs_visual', 'omit', 'unreviewed')
LABELS = dict(zip(STATUSES, ('적절한 그림 있음', '보완 필요', '생략 가능', '근거 부족·미검토')))
REPORT = 'item-visual-audit.json'
DEFAULT_SIGNALS = {
    'state': r'상태|전이|\bstate\b|transition',
    'order': r'순서|단계|먼저|이후|완료|\border\b|\bstep\b|before|after|complet',
    'branch': r'분기|조건|실패|예외|\bif\b|condition|fail|except',
    'responsibility': r'책임|주체|스레드|responsib|thread',
    'ownership': r'소유|수명|반환|재사용|owner|lifetime|return|reuse',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def policy(cfg=None):
    raw = cfg.visual_audit if cfg else {}
    allowed = {'enabled', 'reviews', 'thresholds', 'signals', 'deferred_pages', 'baseline'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('visual_audit accepts enabled, reviews, thresholds, signals, deferred_pages, baseline')
    if type(raw.get('enabled', False)) is not bool:
        raise ValueError('visual_audit.enabled must be boolean')
    baseline = raw.get('baseline')
    if baseline is not None and (not isinstance(baseline,dict) or set(baseline) != {'file','sha256'}
            or not isinstance(baseline.get('file'),str) or not baseline['file']
            or not re.fullmatch(r'[0-9a-f]{64}',str(baseline.get('sha256','')))):
        raise ValueError('visual_audit.baseline requires file and pinned sha256')
    thresholds = {'default': {'chars': 600, 'paragraphs': 3}}
    supplied = raw.get('thresholds', {})
    if not isinstance(supplied, dict):
        raise ValueError('visual_audit.thresholds must map language to thresholds')
    for lang, values in supplied.items():
        if (not isinstance(lang, str) or not isinstance(values, dict)
                or set(values) - {'chars', 'paragraphs', 'rationale'}):
            raise ValueError('visual_audit language thresholds accept chars, paragraphs, rationale')
        if not isinstance(values.get('rationale'), str) or not values['rationale'].strip():
            raise ValueError('Adjusted thresholds require a rationale with actual language examples')
        thresholds[lang] = {**thresholds['default'], **values}
    for values in thresholds.values():
        for key in ('chars', 'paragraphs'):
            if type(values[key]) is not int or values[key] <= 0:
                raise ValueError('visual_audit thresholds must be positive integers')
    if not isinstance(raw.get('signals', {}), dict):
        raise ValueError('visual_audit.signals must be a mapping')
    signals = {**DEFAULT_SIGNALS, **raw.get('signals', {})}
    for name, pattern in signals.items():
        if not isinstance(name, str) or not isinstance(pattern, str) or not pattern:
            raise ValueError('visual_audit signals must be named nonempty regular expressions')
        re.compile(pattern)
    deferred = raw.get('deferred_pages', {})
    if (not isinstance(deferred, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                           or not v.strip() for k, v in deferred.items())):
        raise ValueError('deferred_pages must map page paths to explicit pending review reasons')
    styles = {p.name:hashlib.sha256(read_bytes(p)).hexdigest() for p in sorted(cfg.style_dir.glob('*.md'))} if cfg else {}
    return {**raw, 'thresholds': thresholds, 'signals': signals, 'deferred_pages': deferred, 'style_policy': styles}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children if not isinstance(c, Node) or c.tag != '!')

    def all(self, tag):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.all(tag)


class Document:
    def __init__(self, source):
        from .visual_dom import parse
        self.root = parse(source, Node)


def all_nodes(node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from all_nodes(child)


WINDOW_BINDING = '\n[window binding]\n'


def canonical(node):
    return node if isinstance(node, str) else dict(tag=node.tag, attrs=node.attrs, children=[canonical(c) for c in node.children])


def window_bundle(text, structure, nodes, root, page, *, heading_context=None):
    assets, references = [], []
    for child in nodes:
        if child.attrs.get('href'):
            references.append(child.attrs['href'])
        urls = [child.attrs[k] for k in ('src', 'poster') if child.attrs.get(k)]
        if child.tag in {'image', 'use'}:
            urls.extend(child.attrs[k] for k in ('href', 'xlink:href') if child.attrs.get(k))
        if child.tag == 'object' and child.attrs.get('data'):
            urls.append(child.attrs['data'])
        if child.attrs.get('srcset'):
            for candidate in child.attrs['srcset'].split(','):
                fields = candidate.strip().split()
                if not fields or len(fields) > 2 or (len(fields) == 2 and not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?[wx]', fields[1])):
                    raise ValueError('Unsupported source-window srcset; use explicit local image candidates')
                urls.append(fields[0])
        if re.search(r'url\s*\(', child.attrs.get('style', ''), re.I):
            raise ValueError('Source-window CSS URL assets need explicit local markup')
        for value in urls:
            url = urlsplit(value)
            if url.scheme == 'data':
                continue  # Embedded bytes already participate in canonical attrs.
            if url.scheme or url.netloc:
                raise ValueError('Unfetched external source-window asset: '+value)
            if not url.path and url.fragment:
                raise ValueError('Source-window inline SVG references need an explicit local asset file')
            if root is not None and url.path:
                name = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(url.path)))
                asset = owned_path(root, name)
                if not asset.is_file():
                    raise ValueError('Source window asset missing: '+name)
                assets.append(dict(path=name, sha256=digest(asset.read_bytes().hex())))
    binding = dict(structure_sha256=digest(structure), assets=assets, references=sorted(set(references)))
    if heading_context is not None:
        binding['heading_context'] = heading_context
    return text+WINDOW_BINDING+json.dumps(binding, ensure_ascii=False, sort_keys=True)


def _generated_route_alias(node):
    """Recognize only the renderer's legacy-link control, never hidden prose."""
    if (node.tag != 'div' or node.attrs.get('class') != 'previous-route'
            or not node.attrs.get('id')):
        return False
    nodes = [child for child in node.children if isinstance(child, Node)]
    if (len(nodes) < 2 or nodes[0].tag != 'p'
            or any(not isinstance(child, str) for child in nodes[0].children)
            or plain(nodes[0]) not in {'이전 링크의 목적지', 'Destination of the previous link'}
            or any(node.tag != 'a' or not node.attrs.get('href') for node in nodes[1:])):
        return False
    if any(child.strip() not in {'', '·'} for child in node.children if isinstance(child, str)):
        return False
    phrasing = {'a', 'abbr', 'b', 'bdi', 'bdo', 'br', 'cite', 'code', 'data', 'del', 'dfn',
                'em', 'i', 'ins', 'kbd', 'mark', 'q', 'rp', 'rt', 'ruby', 's', 'samp',
                'small', 'span', 'strong', 'sub', 'sup', 'time', 'u', 'var', 'wbr'}
    return all(child.tag in phrasing
               for link in nodes[1:] for child in all_nodes(link))


def without_navigation(current):
    if isinstance(current,str):
        return current
    return Node(current.tag,dict(current.attrs),[without_navigation(child) for child in current.children
                if not isinstance(child,Node) or child.tag not in {'nav','aside','footer'}])


def node_window(node, root, page, *, heading_context=None, exclude_navigation=False):
    if exclude_navigation:
        node=without_navigation(node)
    return window_bundle(node.text(), canonical(node), list(all_nodes(node)), root, page,
                         heading_context=heading_context)


def source_window(document, fragment, *, root=None, page='', presentation=False):
    """Resolve readable evidence and its owning headings as the browser does."""
    nodes = list(all_nodes(document.root))
    from .site_fragments import fragment_id
    fragment = fragment_id(fragment, {n.attrs['id'] for n in nodes if 'id' in n.attrs})
    found = [n for n in nodes if n.attrs.get('id') == fragment]
    if len(found) != 1:
        raise ValueError('Source window missing or ambiguous: '+fragment)
    parents = {id(c): p for p in nodes for c in p.children if isinstance(c, Node)}
    def inside_navigation(node):
        while node is not document.root:
            if node.tag in {'nav','aside','footer'}:
                return True
            node = parents[id(node)]
        return False
    if inside_navigation(found[0]):
        raise ValueError('Source target is inside excluded navigation: '+fragment)
    owner = found[0]
    while owner is not document.root and owner.tag != 'article':
        owner = parents[id(owner)]
    if owner is document.root:
        raise ValueError('Source target has no owning article: '+fragment)
    scoped_nodes = list(all_nodes(owner))
    outline = {id(node) for node in outline_nodes(document.root)}
    owner_index = next(i for i,node in enumerate(nodes) if node is owner)
    titles = [node for node in nodes[:owner_index] if node.tag == 'h1' and id(node) in outline]
    context, context_nodes = [], []
    for node in ([titles[-1]] if titles else []) + scoped_nodes:
        if inside_navigation(node):
            continue
        heading = bool(re.fullmatch(r'h[1-6]',node.tag)) and id(node) in outline
        if heading:
            while context and int(context[-1]['tag'][1]) >= int(node.tag[1]):
                context.pop()
                context_nodes.pop()
        if node is found[0]:
            break
        if heading:
            context.append(dict(tag=node.tag,id=node.attrs.get('id',''),text=plain(without_navigation(node))))
            context_nodes.append(node)
    def presented(text, selected):
        if not presentation:
            return text
        from .visual_presentation import paths, bind
        ancestry = paths(document.root)
        row = dict(presentation_contexts={})
        for node in [*selected, *(n for h in context_nodes for n in all_nodes(h))]:
            if not inside_navigation(node):
                bind(row, node, ancestry, text=True)
        prose, binding = text.rsplit(WINDOW_BINDING, 1)
        value = json.loads(binding)
        value['presentation_contexts'] = row['presentation_contexts']
        return prose+WINDOW_BINDING+json.dumps(value,ensure_ascii=False,sort_keys=True)
    window = found[0]
    parent = parents.get(id(window))
    anchor = parent if parent and parent.tag == 'p' else window
    container = parents.get(id(anchor))
    if container and re.fullmatch(r'source-[0-9a-f]{16}',fragment):
        position = next(i for i, n in enumerate(container.children) if n is anchor)
        following = next((n for n in container.children[position+1:] if isinstance(n, Node) and n.tag != '!'), None)
        if following and following.tag == 'details':
            ancestor=following
            while ancestor is not document.root and ancestor is not owner:
                ancestor=parents[id(ancestor)]
            if ancestor is not owner:
                raise ValueError('Source panel crosses its owning article boundary: '+fragment)
            text = node_window(following, root, page,heading_context=context+([dict(tag=window.tag,id=fragment,text=plain(without_navigation(window)))] if re.fullmatch(r'h[1-6]',window.tag) else []),exclude_navigation=True)
            return presented(text, [*all_nodes(following), *all_nodes(window)])
    if re.fullmatch(r'h[1-6]', found[0].tag):
        level = int(found[0].tag[1])
        def events(node):
            if isinstance(node, str):
                yield 'text', node
                return
            if node.tag in {'nav','aside','footer'}:
                return
            yield 'start', node
            for child in node.children:
                yield from events(child)
            yield 'end', node
        collecting, parts, structure, selected = False, [], [], []
        for kind, event in events(owner):
            if kind == 'end' and event is owner:
                break
            if kind == 'start':
                if event is found[0]:
                    collecting = True
                elif (collecting and re.fullmatch(r'h[1-6]', event.tag)
                      and id(event) in outline and int(event.tag[1]) <= level):
                    break
                if collecting:
                    selected.append(event)
                    structure.append([kind, event.tag, event.attrs])
            elif collecting:
                if kind == 'text':
                    parts.append(event)
                    structure.append([kind, event])
                else:
                    structure.append([kind, event.tag])
        return presented(window_bundle(''.join(parts), structure, selected, root, page,heading_context=context), selected)
    while window is not owner and window.tag != 'details':
        window = parents[id(window)]
    selected = found[0] if window is owner else window
    return presented(node_window(selected, root, page,heading_context=context,exclude_navigation=True), list(all_nodes(selected)))


def plain(node):
    # Hidden material still participates in fingerprints; it cannot make the
    # candidate shorter. Only source/log/code containers are separated below.
    return ' '.join(node.text().split())


def graph_shape(source):
    """Compare language-independent topology; labels remain separately reviewed."""
    source = re.sub(r'(?m)^\s*%%.*$', '', source)
    source = re.sub(r'"(?:[^"\\]|\\.)*"', '""', source)
    source = re.sub(r'\|[^|]*\|', '||', source)
    return ' '.join(source.split())


def source_container(node):
    classes = set(node.attrs.get('class', '').split())
    if classes & {'evidence-links', 'source-excerpts', 'page-terms', 'manuscript-record', 'scope-notices', 'trace-records'}:
        return True
    summary = next(node.all('summary'), None)
    return bool(summary and re.match(r'(?:소스 근거|Source evidence|설계 질문과 검증 범위|Design questions and verification scope)', plain(summary), re.I))


def outline_nodes(node):
    if isinstance(node, str):
        return
    if (node.tag in {'nav','aside','footer','pre','script','style'}
            or (node.tag == 'details' and source_container(node)) or _generated_route_alias(node)):
        return
    yield node
    for child in node.children:
        yield from outline_nodes(child)


def inventory_page(source, page, options, *, source_commit='', root=None, draft=False):
    doc = Document(source)
    readable = without_navigation(doc.root)
    articles = list(readable.all('article'))
    if len(articles) != 1:
        raise ValueError('Visualization audit requires exactly one readable article: ' + page)
    article = articles[0]
    from .visual_presentation import paths, bind, bind_text
    presentation = paths(readable)
    html = next(doc.root.all('html'), Node('html'))
    lang = html.attrs.get('lang', 'ko')
    thresholds = options['thresholds'].get(lang, options['thresholds']['default'])
    rows, stack, seen = [], [], set()
    active = None
    visual_owner, visual_stack = None, None

    def add(anchor, title, level, node=None):
        locator = anchor or '$heading-'+str(len(rows))
        if locator in seen:
            raise ValueError('Duplicate visualization item anchor: ' + page + '#' + locator)
        seen.add(locator)
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        row = dict(id=page+'#'+locator, page=page, anchor=anchor, url=page+('#'+anchor if anchor else ''), language=lang,
                   title=title, question=title, level=level, parent=stack[-1]['id'] if stack else None,
                   ancestors=[dict(id=p['id'], title=p['title'], level=p['level']) for p in stack],
                   paragraphs=[], loose_text=[], summaries=[], content_blocks=[], tables=[], figures=[], available_source_windows=[], excluded=[], children=[], presentation_contexts={}, heading_contexts={})
        if node is not None:
            bind(row, node, presentation, subtree=True)
            row['heading_contexts'] = dict(row['presentation_contexts'])
        for parent in stack:
            row['presentation_contexts'].update(parent['heading_contexts'])
        if stack:
            stack[-1]['children'].append(row['id'])
        rows.append(row)
        stack.append(row)
        return row

    nodes = list(outline_nodes(readable))
    article_index = next(i for i,node in enumerate(nodes) if node is article)
    page_titles = [node for node in nodes[:article_index] if node.tag == 'h1']
    current = add(None, 'Page introduction', 1, page_titles[-1] if page_titles else None)

    def flush_loose(row):
        if row['loose_text']:
            row['paragraphs'].append(' '.join(' '.join(row['loose_text']).split()))
            row['loose_text'].clear()

    def walk(node, parent=None, position=0):
        nonlocal current, active, visual_owner, visual_stack
        if isinstance(node, str):
            if parent is not None and node.strip():
                bind_text(current, parent, position, node, presentation)
                if active is not None:
                    bind_text(visual_owner, parent, position, node, presentation)
            if active is not None:
                active['text'].append(node)
            elif node.strip():
                current['loose_text'].append(node)
            return
        if node.tag == '!':
            value = node.attrs['value']
            match = re.fullmatch(r'sdd:visual:([a-z][a-z0-9_-]*)', value)
            if match or value == 'sdd:class-diagram':
                if active is not None:
                    raise ValueError('Nested visualization marker: '+page)
                visual_owner, visual_stack = current, list(stack)
                active = dict(id=match[1] if match else 'class-diagram', source='', evidence=[], downloads=[], convenience_designations=[], evidence_groups=[], text=[], markup_bindings=[], heading_count=0)
                current['figures'].append(active)
            elif value.startswith('/sdd:visual:') or value == '/sdd:class-diagram':
                expected = ('/sdd:class-diagram' if active and active['id'] == 'class-diagram'
                            else '/sdd:visual:'+active['id'] if active else None)
                if value != expected:
                    raise ValueError('Unmatched visualization marker: '+page)
                active = None
                current, stack[:] = visual_owner, visual_stack
                visual_owner, visual_stack = None, None
            elif value.startswith(('sdd:visual:', '/sdd:visual:', 'sdd:class-diagram', '/sdd:class-diagram')):
                raise ValueError('Malformed visualization marker: '+page)
            return
        if re.fullmatch(r'h[1-6]', node.tag) and any(
            child.tag in {'pre','script','style'} or (child.tag == 'details' and source_container(child))
            or _generated_route_alias(child) for child in all_nodes(node) if child is not node):
            raise ValueError('Reader heading contains a source/log container; separate its evidence: '+page)
        if active is not None:
            bind(current, node, presentation)
            bind(visual_owner, node, presentation, text=True)
            active['markup_bindings'].append(digest(node_window(node, root, page)))
            if re.fullmatch(r'h[1-6]', node.tag):
                # Explanation stages are H3 questions; their generated figure
                # titles are H4. Keep that title inventoried, and continue to
                # reject extra headings or an H4 without its H3 owner.
                stage_title = node.tag == 'h4' and visual_owner['level'] == 3
                if (node.tag not in {'h2', 'h3'} and not stage_title) or active['heading_count']:
                    raise ValueError('Ordinary section inside visualization marker: '+page)
                active['heading_count'] += 1
                # Inventory the title too. A marker must never make a real
                # question disappear, even when it is the block's first title.
                current = add(node.attrs.get('id'), plain(node), int(node.tag[1]), node)
                bind(current, node, presentation, subtree=True)
                current['role'] = 'visual_title'
                current['figures'].append(active)
            if node.tag == 'pre' and 'mermaid' in node.attrs.get('class', '').split():
                bind(current, node, presentation, subtree=True)
                bind(visual_owner, node, presentation, subtree=True)
                active['source'] += node.text()
                return
            if node.tag == 'p':
                links = list(node.all('a'))
                downloads = [a for a in links if urlsplit(a.attrs.get('href', '')).path.endswith('.mmd')]
                download_only = len(downloads) == 1 and plain(node) == plain(downloads[0])
                if not download_only and plain(node):
                    current['paragraphs'].append(plain(node))
            if node.tag == 'a':
                href = node.attrs.get('href', '')
                if node.attrs.get('data-sdd-convenience') == 'true':
                    active['convenience_designations'].append(href)
                active['downloads' if urlsplit(href).path.endswith('.mmd') else 'evidence'].append(href)
            if node.tag == 'details':
                bind(current, node, presentation, subtree=True)
                bind(visual_owner, node, presentation, subtree=True)
                active['text'].append(plain(node))
                active['evidence'].extend(a.attrs.get('href', '') for a in node.all('a'))
                active['convenience_designations'].extend(a.attrs.get('href', '') for a in node.all('a') if a.attrs.get('data-sdd-convenience') == 'true')
                active['evidence_groups'].extend([[a.attrs.get('href', '') for a in tr.all('a')] for tr in node.all('tr')])
                if any(re.fullmatch(r'h[1-6]', n.tag) for n in all_nodes(node) if n is not node):
                    raise ValueError('Ordinary section inside visualization marker: '+page)
                summary = next(node.all('summary'), None)
                evidence_note = summary and re.match(r'(?:그림 근거와 확인 범위|Figure evidence|Diagram evidence)', plain(summary), re.I)
                if source_container(node) or evidence_note:
                    return
            for index,child in enumerate(node.children):
                walk(child, node, index)
            return
        if node.tag in {'pre', 'script', 'style'} or (node.tag == 'details' and source_container(node)):
            bind(current, node, presentation, subtree=True)
            current['excluded'].append(dict(kind=node.tag, chars=len(plain(node)), sha256=digest(node_window(node, root, page)),
                                            markup_sha256=digest(canonical(node)),
                                            presentation_context=presentation[id(node)]))
            for link in node.all('a'):
                href = link.attrs.get('href', '')
                if href:
                    current['available_source_windows'].append(href)
            if node.tag == 'pre' and 'mermaid' in node.attrs.get('class', '').split():
                current['figures'].append(dict(id='mermaid-'+str(len(current['figures'])), source=node.text(), evidence=[], text=[]))
            return
        if _generated_route_alias(node):
            bind(current, node, presentation, subtree=True)
            # Exclude only explanation counting. Keep the full control in
            # source windows and fingerprints, and retain explicit citations.
            binding = digest(node_window(node, root, page))
            current['excluded'].append(dict(kind='navigation', chars=len(plain(node)), sha256=binding,
                                            markup_sha256=digest(canonical(node)),
                                            presentation_context=presentation[id(node)]))
            current['content_blocks'].append(binding)
            current['available_source_windows'].extend(
                link.attrs.get('href', '') for link in node.all('a')
                if 'citation' in link.attrs.get('class', '').split())
            return
        descendants = [child for child in all_nodes(node) if child is not node]
        heading_children = any(re.fullmatch(r'h[1-6]', child.tag) for child in descendants)
        separate_children = heading_children or any(
            child.tag in {'pre','script','style'} or (child.tag == 'details' and source_container(child))
            or _generated_route_alias(child) for child in descendants)
        block = node.tag in {'p','li','div','section','blockquote','summary','table'} or re.fullmatch(r'h[1-6]', node.tag)
        if block:
            flush_loose(current)
        if node.tag == 'summary' and not separate_children:
            bind(current, node, presentation, subtree=True)
            current['summaries'].append(plain(node))
            current['content_blocks'].append(digest(node_window(node, root, page)))
            return
        if re.fullmatch(r'h[1-6]', node.tag):
            anchor = node.attrs.get('id')
            current = add(anchor, plain(node), int(node.tag[1]), node)
            bind(current, node, presentation, subtree=True)
            return
        if node.tag == 'table' and not separate_children:
            bind(current, node, presentation, subtree=True)
            current['tables'].append(plain(node))
            current['content_blocks'].append(digest(node_window(node, root, page)))
            return
        simple_container = node.tag in {'div', 'blockquote', 'section', 'figcaption'} and not any(
            n.tag in {'p', 'li', 'table', 'details', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'} for n in descendants)
        if not separate_children and (node.tag == 'p' or simple_container or (node.tag == 'li' and not list(node.all('p')) and not list(node.all('li')))):
            bind(current, node, presentation, subtree=True)
            current['content_blocks'].append(digest(node_window(node, root, page)))
            value = plain(node)
            if value:
                current['paragraphs'].append(value)
            for link in node.all('a'):
                if 'citation' in link.attrs.get('class', '').split():
                    current['available_source_windows'].append(link.attrs.get('href', ''))
            return
        if not node.children:
            bind(current, node, presentation)
            current['content_blocks'].append(digest(node_window(node, root, page)))
        for index,child in enumerate(node.children):
            walk(child, node, index)
        if block:
            flush_loose(current)

    walk(article)
    if active is not None:
        raise ValueError('Unclosed visualization marker: '+page)
    by_id = {row['id']: row for row in rows}
    window_hashes, window_references = {}, {}
    for row in reversed(rows):
        if row['loose_text']:
            row['paragraphs'].append(' '.join(' '.join(row['loose_text']).split()))
        body = '\n\n'.join(row['paragraphs'])
        text = row['title']+'\n'+body+'\n'+'\n'.join(row['tables'])
        row['body'] = body
        row['body_chars'], row['paragraph_count'] = len(body), len(row['paragraphs'])
        row['complexity_signals'] = [name for name, pattern in options['signals'].items() if re.search(pattern, text, re.I)]
        row['candidate_reasons'] = (['long_explanation'] if len(body) >= thresholds['chars'] else [])
        if len(row['paragraphs']) >= thresholds['paragraphs']:
            row['candidate_reasons'].append('multiple_paragraphs')
        if row['complexity_signals']:
            row['candidate_reasons'].append('possible_complexity')
        row['table_count'] = len(row['tables'])
        row['figures'] = [{**f, 'sha256': digest(f)} for f in row['figures']]
        row['available_source_windows'] = sorted(set(row['available_source_windows']))
        document_hash = digest(dict(title=row['title'], body=body, tables=row['tables'], content_blocks=row['content_blocks']))
        row['source_window_hashes'] = {'item:'+row['id']: document_hash}
        if row['anchor']:
            row['source_window_hashes'][row['id']] = document_hash
        row['unresolved_source_windows'] = []
        row['source_window_references'] = {}
        for href in row['available_source_windows']+[u for f in row['figures'] for u in f['evidence']]:
            parts = urlsplit(href)
            if not parts.scheme and not parts.netloc and parts.path and not parts.fragment:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(parts.path)))
                if root is None:
                    row['unresolved_source_windows'].append(href)
                    continue
                path = owned_path(root, target)
                if not path.is_file():
                    row['unresolved_source_windows'].append(href)
                    continue
                row['source_window_hashes'][target] = digest(path.read_bytes().hex())
                continue
            if not parts.scheme and not parts.netloc and parts.fragment:
                fragment = parts.fragment
                target = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(parts.path))) if parts.path else page
                key = target+'#'+fragment
                if key not in window_hashes:
                    if target == page:
                        selected = source_window(doc, fragment, root=root, page=page, presentation=True)
                        window_hashes[key] = digest(selected)
                        window_references[key] = json.loads(selected.rsplit(WINDOW_BINDING, 1)[1])['references']
                    elif root is not None:
                        path = owned_path(root, target)
                        if not path.is_file():
                            row['unresolved_source_windows'].append(href)
                            continue
                        raw = path.read_text(encoding='utf-8')
                        if path.suffix == '.html':
                            selected = source_window(Document(raw), fragment, root=root, page=target, presentation=True)
                        else:
                            lines = re.fullmatch(r'L([1-9][0-9]*)(?:-L([1-9][0-9]*))?', unquote(fragment))
                            if not lines:
                                row['unresolved_source_windows'].append(href)
                                continue
                            first = int(lines[1])
                            last = int(lines[2] or lines[1])
                            if first > last or last > len(raw.splitlines()):
                                raise ValueError('Source window line range is invalid: '+key)
                        # Keep the existing conservative cross-file byte pin.
                        # The separately supplied selected window is the actual
                        # review scope; a file hash never claims whole-file review.
                        window_hashes[key] = digest([path.read_bytes().hex(), selected] if path.suffix == '.html' else path.read_bytes().hex())
                        window_references[key] = json.loads(selected.rsplit(WINDOW_BINDING, 1)[1])['references'] if path.suffix == '.html' else []
                    else:
                        row['unresolved_source_windows'].append(href)
                        continue
                row['source_window_hashes'][key] = window_hashes[key]
                row['source_window_references'][key] = window_references[key]
            elif parts.scheme or parts.netloc:
                row['unresolved_source_windows'].append(href)
        for figure in row['figures']:
            figure['download_bindings'] = []
            for href in figure.get('downloads', []):
                url = urlsplit(href)
                if url.scheme or url.netloc or url.query or url.fragment or not url.path:
                    raise ValueError('Unsupported visualization download: '+href)
                name = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(url.path)))
                expected = figure['source']+'\n'  # Exporter's explicit UTF-8/LF serialization.
                if draft:
                    figure['download_bindings'].append(dict(path=name, kind='derived-after-draft', source_sha256=digest(expected)))
                else:
                    if root is None:
                        raise ValueError('Visualization download needs a publication root: '+href)
                    path = owned_path(root, name)
                    if not path.is_file() or path.read_bytes() != expected.encode('utf-8'):
                        raise ValueError('Visualization download missing or differs from inline figure: '+href)
                    figure['download_bindings'].append(dict(path=name, kind='published-file', sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            selected_evidence, convenience = [], []
            for href in figure['evidence']:
                url = urlsplit(href)
                binding = None
                if (url.scheme or url.netloc) and href in figure.get('convenience_designations', []):
                    for group in figure.get('evidence_groups', []):
                        if href not in group:
                            continue
                        for local in group:
                            loc = urlsplit(local)
                            if loc.scheme or loc.netloc:
                                continue
                            name = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(loc.path))) if loc.path else page
                            key = name+('#'+loc.fragment if loc.fragment else '')
                            if href in row['source_window_references'].get(key, []):
                                binding = dict(url=href, local_window=key, local_sha256=row['source_window_hashes'][key], external_fetched=False)
                                break
                        if binding:
                            break
                if binding:
                    convenience.append(binding)
                    row['unresolved_source_windows'] = [u for u in row['unresolved_source_windows'] if u != href]
                else:
                    selected_evidence.append(href)
            figure['evidence'] = selected_evidence
            figure['convenience_links'] = convenience
            figure.pop('sha256', None)
            figure['sha256'] = digest(figure)
        row['source_commit'] = source_commit
        row['fingerprint'] = digest({**row, 'child_fingerprints': [by_id[c]['fingerprint'] for c in row['children']],
                                     'policy': {k: options[k] for k in ('thresholds', 'signals', 'style_policy')}, 'version': 1})
        row['status'] = 'unreviewed'
        row['reason'] = options['deferred_pages'].get(page, 'No current item review; candidate heuristics are not acceptance')
        row['source_windows'] = []
        row['unreviewed_scope'] = ['Meaning, visualization suitability and source grounding have not been reviewed']
    return rows


def inspect_site(root, options, *, manifest=None, source_commit=''):
    """The manifest is authoritative when supplied; staging uses every HTML file."""
    root = Path(root).resolve()
    files = sorted(rel for rel in manifest['outputs'] if rel.endswith('.html')) if manifest else sorted(p.relative_to(root).as_posix() for p in root.rglob('*.html'))
    rows = []
    commits = set()
    for rel in files:
        from .document_metadata import split_frontmatter
        manuscript = owned_path(root, rel.removeprefix('en/')).with_suffix('.md')
        recorded_commit = (split_frontmatter(manuscript.read_text(encoding='utf-8'))[0].get('source_commit', '')
                           if manuscript.is_file() else '')
        if recorded_commit:
            commits.add(recorded_commit)
        if source_commit and recorded_commit and recorded_commit != source_commit:
            raise ValueError('Visualization manuscript and facts commits differ: '+rel)
        # Rendered HTML is a staging output, not an immutable source input.
        # Pinning it as an input would reject the normal temporary-dir cleanup.
        rows.extend(inventory_page(owned_path(root, rel).read_text(encoding='utf-8'), rel, options,
                                   source_commit=recorded_commit or source_commit, root=root))
    if len(commits) > 1:
        raise ValueError('Visualization inventory contains manuscripts from different source commits')
    pairs = {}
    for row in rows:
        canonical = row['id'].removeprefix('en/')
        pairs.setdefault(canonical, []).append(row)
    errors = []
    for page in options['deferred_pages']:
        if page not in files:
            errors.append('Deferred page missing from inventory: '+page)
    bilingual = any(name.startswith('en/') for name in files)
    if bilingual:
        for key, values in pairs.items():
            if len(values) != 2 or {v['language'] for v in values} != {'ko', 'en'}:
                errors.append('Bilingual item missing or ambiguous: '+key)
            elif [(f['id'], graph_shape(f['source'])) for f in values[0]['figures']] != [(f['id'], graph_shape(f['source'])) for f in values[1]['figures']]:
                errors.append('Bilingual item figures differ: '+key)
    return dict(schema=1, policy=options, source_commit=source_commit or next(iter(commits), ''), pages=files,
                baseline_build_id=manifest.get('build_id') if manifest else None,
                items=rows, errors=errors, human_review='pending')


def apply_reviews(report, reviews):
    if reviews.get('schema') != 1 or not isinstance(reviews.get('items'), dict):
        raise ValueError('Visualization reviews require schema 1 and an items mapping')
    if 'pages' in report:
        missing = set(reviews['items'])-{r['id'] for r in report['items']}
        report['errors'].extend('Reviewed item deleted or moved: '+key for key in sorted(missing))
    for row in report['items']:
        record = reviews['items'].get(row['id'])
        if not record:
            continue
        if not isinstance(record, dict):
            raise ValueError('Visualization item review must be an object: '+row['id'])
        errors = []
        if record.get('fingerprint') != row['fingerprint']:
            errors.append('Item, hierarchy, figure, source or policy changed; review again')
        status = record.get('status')
        if status not in STATUSES:
            errors.append('Invalid review status')
        for key in ('reason', 'question'):
            if not isinstance(record.get(key), str) or not record[key].strip():
                errors.append('Review needs '+key)
        windows = record.get('source_windows')
        scope = record.get('unreviewed_scope')
        accepted = status in {'appropriate', 'omit'}
        if not isinstance(windows, list) or (accepted and not windows) or any(not isinstance(w, str) or not w.strip() for w in windows):
            errors.append('Review must state actual reviewed source/document windows')
        if not isinstance(scope, list) or (accepted and scope):
            errors.append('Unreviewed scope remains')
        if isinstance(windows, list) and any(w not in row['source_window_hashes'] for w in windows):
            errors.append('Unknown or unresolved reviewed source/document window')
        if row['page'] in report['policy']['deferred_pages']:
            errors.append('Another session owns this page; integration review pending')
        if status == 'appropriate':
            figures = record.get('figures')
            available = {f['id'] for f in row['figures'] if f['source']}
            # Adjacent reuse must explicitly name the reviewed item on the same page.
            adjacent = record.get('adjacent_item')
            if adjacent:
                neighbor = next((r for r in report['items'] if r['id'] == adjacent), None)
                siblings = [r['id'] for r in report['items'] if r['page'] == row['page'] and r['parent'] == row['parent']]
                if (neighbor is None or neighbor['page'] != row['page'] or neighbor['parent'] != row['parent']
                        or abs(siblings.index(row['id'])-siblings.index(neighbor['id'])) != 1):
                    errors.append('Adjacent figure must belong to a sibling item on this page')
                else:
                    available |= {f['id'] for f in neighbor['figures'] if f['source']}
                    if record.get('adjacent_fingerprint') != neighbor['fingerprint']:
                        errors.append('Adjacent figure changed')
            if not isinstance(figures, list) or not figures or not set(figures) <= available:
                errors.append('Reviewed local figure missing, deleted or stale-omitted')
            else:
                def local_key(href):
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        return None
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(row['page']), unquote(url.path))) if url.path else row['page']
                    return target+('#'+url.fragment if url.fragment else '')
                owned_figures = [(row, f) for f in row['figures']]
                if adjacent and neighbor is not None:
                    owned_figures.extend((neighbor, f) for f in neighbor['figures'])
                for owner, figure in owned_figures:
                    if figure['id'] not in figures:
                        continue
                    for href in figure['evidence']:
                        key = local_key(href)
                        if key is not None:
                            resolved = key in owner['source_window_hashes']
                        else:
                            # Explicitly bound convenience links were removed
                            # from selected evidence during fresh inspection.
                            resolved = False
                        if not resolved:
                            errors.append('Reviewed figure evidence window is unresolved: '+href)
        if errors:
            row.update(status='unreviewed', reason='; '.join(errors))
        else:
            row.update({k: record[k] for k in ('status', 'reason', 'question', 'source_windows', 'unreviewed_scope')})
            row['reviewed_figures'] = record.get('figures', [])
            row['review_method'] = record.get('review_method', 'editorial-record')
            for key in ('adjacent_item', 'adjacent_fingerprint'):
                if key in record:
                    row[key] = record[key]
    peers = {}
    for row in report['items']:
        peers.setdefault(row['id'].removeprefix('en/'), []).append(row)
    for values in peers.values():
        if len(values) == 2 and {r['status'] for r in values} == {'appropriate', 'omit'}:
            report['errors'].append('Bilingual visualization judgments differ: '+values[0]['id'])
    counts = Counter(row['status'] for row in report['items'])
    report['counts'] = {s: counts[s] for s in STATUSES}
    report['unresolved'] = counts['needs_visual']+counts['unreviewed']
    for row in report['items']:
        row['judgment'] = LABELS[row['status']]
    return report


def verify_published(root, manifest):
    """Recompute item fingerprints in verify-site, not just the report's hash."""
    if REPORT not in manifest['outputs']:
        if manifest.get('inputs',{}).get('item_visual_baseline') or manifest.get('inputs',{}).get('item_visual_retention'):
            raise ValueError('Published visualization baseline requires its audit report')
        return
    recorded = json.loads(owned_path(root, REPORT).read_bytes())
    report = inspect_site(root, recorded['policy'], manifest=manifest, source_commit=recorded['source_commit'])
    records = {r['id']: {**r, 'figures': r.get('reviewed_figures', [])} for r in recorded['items']}
    if set(records) != {r['id'] for r in report['items']}:
        raise ValueError('Published visualization item set changed')
    apply_reviews(report, dict(schema=1, items=records))
    baseline=recorded['policy'].get('baseline')
    retained=recorded.get('baseline_retention')
    pinned=manifest.get('inputs',{}).get('item_visual_baseline')
    contract_digest=manifest.get('inputs',{}).get('item_visual_retention')
    if baseline or retained or pinned or contract_digest:
        if (not isinstance(baseline,dict) or not isinstance(retained,dict)
                or not re.fullmatch(r'[0-9a-f]{64}',str(pinned))
                or retained.get('sha256') != pinned or baseline.get('sha256') != pinned
                or contract_digest != digest(retained)):
            raise ValueError('Published visualization baseline retention contract missing or changed')
        retain_baseline_items(report,retained)
    enforce(report)


def baseline_contract(cfg, options):
    """Retain the actual previous item set even when a new ledger is complete."""
    spec = options.get('baseline')
    if spec is None:
        return None
    path = cfg.root/spec['file']
    raw = read_bytes(path)
    if hashlib.sha256(raw).hexdigest() != spec['sha256']:
        raise ValueError('Visualization baseline digest changed')
    data = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    if not isinstance(data,dict) or data.get('schema') != 1 or not isinstance(data.get('items'),list) or not data['items']:
        raise ValueError('Visualization baseline requires a schema1 inventory')
    required, positional = {}, {}
    seen = set()
    for row in data['items']:
        if (not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id']
                or row['id'] in seen or not re.fullmatch(r'[0-9a-f]{64}',str(row.get('fingerprint','')))):
            raise ValueError('Visualization baseline has invalid or duplicate item identities')
        seen.add(row['id'])
        if row.get('role') != 'visual_title':
            required[row['id']] = row['fingerprint']
            if re.search(r'#\$heading-[0-9]+$',row['id']):
                if row.get('level') != 1 or row.get('title') != 'Page introduction':
                    raise ValueError('Retained reader questions require persistent explicit anchors: '+row['id'])
                identity = {key:row.get(key) for key in ('title','level','ancestors')}
                if not isinstance(identity['title'],str) or not isinstance(identity['level'],int) or not isinstance(identity['ancestors'],list):
                    raise ValueError('Positional baseline items require their heading identity')
                positional[row['id']] = identity
    if not required:
        raise ValueError('Visualization baseline contains no reader questions')
    return dict(schema=1,sha256=spec['sha256'],source_commit=data.get('source_commit',''),
                build_id=data.get('baseline_build_id'),required_items=required,positional_identities=positional,
                scope='Stable reader-question identities only; no historical review or figure approval is reused')


def retain_baseline_items(report, contract):
    if (not isinstance(contract,dict) or contract.get('schema') != 1
            or not re.fullmatch(r'[0-9a-f]{64}',str(contract.get('sha256','')))
            or not isinstance(contract.get('required_items'),dict) or not contract['required_items']
            or any(not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{64}',str(value))
                   for key,value in contract['required_items'].items())):
        raise ValueError('Invalid published baseline retention contract')
    current = {row['id']:row for row in report['items']}
    identities=contract.get('positional_identities')
    if (not isinstance(identities,dict) or set(identities) != {key for key in contract['required_items'] if re.search(r'#\$heading-[0-9]+$',key)}
            or any(not isinstance(value,dict) or set(value) != {'title','level','ancestors'} for value in identities.values())):
        raise ValueError('Invalid positional baseline heading identities')
    missing = [key for key in contract['required_items']
               if key not in current or current[key].get('role') == 'visual_title']
    report['errors'].extend('Baseline reader question deleted or replaced by a figure title: '+key for key in sorted(missing))
    for key,identity in identities.items():
        if key in current and any(current[key].get(name)!=value for name,value in identity.items()):
            report['errors'].append('Positional baseline reader question changed identity; retain an explicit anchor or review a new baseline: '+key)
    report['baseline_retention'] = contract
    return report


def enforce(report):
    if report['errors'] or report['unresolved']:
        raise ValueError(f"Item visualization review incomplete: {report['unresolved']} unresolved; " + '; '.join(report['errors'][:8]))


def publication_gate(cfg, stage):
    options = policy(cfg)
    if not options.get('enabled', False):
        return
    if not options.get('reviews'):
        raise ValueError('visual_audit.enabled requires a reviews file')
    commit = load_json(cfg.facts_path).get('meta', {}).get('source_commit', '') if cfg.facts_path.exists() else ''
    report = inspect_site(stage, options, source_commit=commit)
    apply_reviews(report, load_json(cfg.root/options['reviews']))
    if contract := baseline_contract(cfg,options):
        retain_baseline_items(report,contract)
    enforce(report)
    (stage/REPORT).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')


def manuscript_gate(cfg, model, path, text):
    """Check assembled draft items without extending focused response JSON.

    Draft and final HTML reviews have distinct fingerprints and ledger entries;
    a draft review cannot stand in for final bilingual publication acceptance.
    """
    options = policy(cfg)
    if not options.get('enabled', False):
        return
    if not options.get('reviews'):
        raise ValueError('visual_audit.enabled requires a reviews file')
    from .document_metadata import split_frontmatter
    from .site_markdown import _render, _html_path
    rel = path.relative_to(cfg.sdd_dir).as_posix()
    meta, body = split_frontmatter(text)
    commit = model.meta.get('source_commit', '')
    if meta.get('source_commit') != commit:
        raise ValueError('Visualization manuscript and facts commits differ')
    content, _, _ = _render(body, rel, {rel}, model, '', commit)
    rows = inventory_page('<html lang="ko"><article>'+content+'</article></html>',
                          _html_path(rel), options, source_commit=commit, root=cfg.sdd_dir, draft=True)
    records = load_json(cfg.root/options['reviews'])
    report = dict(items=rows, errors=[], policy=options)
    apply_reviews(report, {'schema': records.get('schema'), 'items': records.get('manuscripts', {})})
    enforce(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--source-commit', default='')
    parser.add_argument('--enforce', action='store_true')
    args = parser.parse_args()
    from .config import load
    manifest = load_json(args.site/'site-manifest.json')
    report = inspect_site(args.site, policy(load(args.config) if args.config else None), manifest=manifest, source_commit=args.source_commit)
    apply_reviews(report, load_json(args.reviews) if args.reviews else {'schema': 1, 'items': {}})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(pages=len(report['pages']), items=len(report['items']), counts=report['counts'], errors=report['errors']), ensure_ascii=False))
    if args.enforce:
        enforce(report)


if __name__ == '__main__':
    main()
