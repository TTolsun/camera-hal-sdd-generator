"""Per-item visualization inventory and an opt-in, fail-closed publication gate.

Candidate heuristics never grant acceptance. A review binds the explanation,
heading ancestry, descendant items, local figures and source windows. This is
an editorial/automated review record, not human approval or runtime evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit

from .validation_stage import load_json

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
    raw = cfg.raw.get('visual_audit', {}) if cfg else {}
    allowed = {'enabled', 'reviews', 'thresholds', 'signals', 'deferred_pages'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('visual_audit accepts enabled, reviews, thresholds, signals, deferred_pages')
    if type(raw.get('enabled', False)) is not bool:
        raise ValueError('visual_audit.enabled must be boolean')
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
    return {**raw, 'thresholds': thresholds, 'signals': signals, 'deferred_pages': deferred}


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


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)

    def handle_comment(self, value):
        self.stack[-1].children.append(Node('!', {'value': value.strip()}))


def all_nodes(node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from all_nodes(child)


def source_window(document, fragment):
    """Resolve an empty source anchor to its precise folded excerpt, not the list."""
    nodes = list(all_nodes(document.root))
    found = [n for n in nodes if n.attrs.get('id') == fragment]
    if len(found) != 1:
        raise ValueError('Source window missing or ambiguous: '+fragment)
    parents = {id(c): p for p in nodes for c in p.children if isinstance(c, Node)}
    window = found[0]
    parent = parents.get(id(window))
    container = parents.get(id(parent)) if parent else None
    if (parent and container and parent.tag == 'p' and not parent.text().strip()
            and 'source-excerpts' in container.attrs.get('class', '').split()):
        position = next(i for i, n in enumerate(container.children) if n is parent)
        following = next((n for n in container.children[position+1:] if isinstance(n, Node)), None)
        if following and following.tag == 'details':
            return following.text()
    while window is not document.root and window.tag != 'details':
        window = parents[id(window)]
    return (found[0] if window is document.root else window).text()


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


def inventory_page(source, page, options, *, source_commit='', root=None):
    doc = Document(source)
    article = next(doc.root.all('article'), None)
    if article is None:
        raise ValueError('Visualization audit requires an article: ' + page)
    html = next(doc.root.all('html'), Node('html'))
    lang = html.attrs.get('lang', 'ko')
    thresholds = options['thresholds'].get(lang, options['thresholds']['default'])
    rows, stack, seen = [], [], set()
    active = None
    visual_owner, visual_stack = None, None

    def add(anchor, title, level):
        locator = anchor or '$heading-'+str(len(rows))
        if locator in seen:
            raise ValueError('Duplicate visualization item anchor: ' + page + '#' + locator)
        seen.add(locator)
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        row = dict(id=page+'#'+locator, page=page, anchor=anchor, url=page+('#'+anchor if anchor else ''), language=lang,
                   title=title, question=title, level=level, parent=stack[-1]['id'] if stack else None,
                   ancestors=[dict(id=p['id'], title=p['title'], level=p['level']) for p in stack],
                   paragraphs=[], loose_text=[], summaries=[], tables=[], figures=[], available_source_windows=[], excluded=[], children=[])
        if stack:
            stack[-1]['children'].append(row['id'])
        rows.append(row)
        stack.append(row)
        return row

    current = add(None, 'Page introduction', 1)

    def walk(node):
        nonlocal current, active, visual_owner, visual_stack
        if isinstance(node, str):
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
                active = dict(id=match[1] if match else 'class-diagram', source='', evidence=[], text=[], heading_count=0)
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
        if active is not None:
            if re.fullmatch(r'h[1-6]', node.tag):
                if node.tag not in {'h2', 'h3'} or active['heading_count']:
                    raise ValueError('Ordinary section inside visualization marker: '+page)
                active['heading_count'] += 1
                # Inventory the title too. A marker must never make a real
                # question disappear, even when it is the block's first title.
                current = add(node.attrs.get('id'), plain(node), int(node.tag[1]))
                current['role'] = 'visual_title'
                current['figures'].append(active)
            if node.tag == 'pre' and 'mermaid' in node.attrs.get('class', '').split():
                active['source'] += node.text()
                return
            if node.tag == 'p':
                links = list(node.all('a'))
                downloads = [a for a in links if urlsplit(a.attrs.get('href', '')).path.endswith('.mmd')]
                download_only = len(downloads) == 1 and plain(node) == plain(downloads[0])
                if not download_only and plain(node):
                    current['paragraphs'].append(plain(node))
            if node.tag == 'a':
                active['evidence'].append(node.attrs.get('href', ''))
            if node.tag == 'details':
                active['text'].append(plain(node))
                active['evidence'].extend(a.attrs.get('href', '') for a in node.all('a'))
                if any(re.fullmatch(r'h[1-6]', n.tag) for n in all_nodes(node) if n is not node):
                    raise ValueError('Ordinary section inside visualization marker: '+page)
                summary = next(node.all('summary'), None)
                evidence_note = summary and re.match(r'(?:그림 근거와 확인 범위|Figure evidence|Diagram evidence)', plain(summary), re.I)
                if source_container(node) or evidence_note:
                    return
            for child in node.children:
                walk(child)
            return
        if node.tag in {'pre', 'script', 'style'} or (node.tag == 'details' and source_container(node)):
            current['excluded'].append(dict(kind=node.tag, chars=len(plain(node)), sha256=digest(node.text())))
            for link in node.all('a'):
                href = link.attrs.get('href', '')
                if href:
                    current['available_source_windows'].append(href)
            if node.tag == 'pre' and 'mermaid' in node.attrs.get('class', '').split():
                current['figures'].append(dict(id='mermaid-'+str(len(current['figures'])), source=node.text(), evidence=[], text=[]))
            return
        if node.tag == 'summary':
            current['summaries'].append(plain(node))
            return
        if re.fullmatch(r'h[2-6]', node.tag):
            anchor = node.attrs.get('id')
            current = add(anchor, plain(node), int(node.tag[1]))
            return
        if node.tag == 'table':
            current['tables'].append(plain(node))
            return
        simple_container = node.tag in {'div', 'blockquote', 'section', 'figcaption'} and not any(
            n.tag in {'p', 'li', 'table', 'details', 'pre', 'h2', 'h3', 'h4', 'h5', 'h6'} for n in all_nodes(node) if n is not node)
        if node.tag == 'p' or simple_container or (node.tag == 'li' and not list(node.all('p')) and not list(node.all('li'))):
            value = plain(node)
            if value:
                current['paragraphs'].append(value)
            for link in node.all('a'):
                if 'citation' in link.attrs.get('class', '').split():
                    current['available_source_windows'].append(link.attrs.get('href', ''))
            return
        for child in node.children:
            walk(child)

    walk(article)
    if active is not None:
        raise ValueError('Unclosed visualization marker: '+page)
    by_id = {row['id']: row for row in rows}
    window_hashes = {}
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
        document_hash = digest(dict(title=row['title'], body=body, tables=row['tables']))
        row['source_window_hashes'] = {'item:'+row['id']: document_hash}
        if row['anchor']:
            row['source_window_hashes'][row['id']] = document_hash
        row['unresolved_source_windows'] = []
        for href in row['available_source_windows']+[u for f in row['figures'] for u in f['evidence']]:
            parts = urlsplit(href)
            if not parts.scheme and not parts.netloc and parts.fragment:
                fragment = unquote(parts.fragment)
                target = posixpath.normpath(posixpath.join(posixpath.dirname(page), unquote(parts.path))) if parts.path else page
                key = target+'#'+fragment
                if key not in window_hashes:
                    if target == page:
                        window_hashes[key] = digest(source_window(doc, fragment))
                    elif root is not None:
                        from .site_build import owned_path
                        path = owned_path(root, target)
                        if not path.is_file():
                            row['unresolved_source_windows'].append(href)
                            continue
                        raw = path.read_text(encoding='utf-8')
                        if path.suffix == '.html':
                            source_window(Document(raw), fragment)
                        else:
                            lines = re.fullmatch(r'L([1-9][0-9]*)(?:-L([1-9][0-9]*))?', fragment)
                            if not lines:
                                row['unresolved_source_windows'].append(href)
                                continue
                            first = int(lines[1])
                            last = int(lines[2] or lines[1])
                            if first > last or last > len(raw.splitlines()):
                                raise ValueError('Source window line range is invalid: '+key)
                        # Cross-file windows bind all target bytes so an edit
                        # next to a line anchor cannot escape revalidation.
                        window_hashes[key] = digest(raw)
                    else:
                        row['unresolved_source_windows'].append(href)
                        continue
                row['source_window_hashes'][key] = window_hashes[key]
            elif parts.scheme or parts.netloc:
                row['unresolved_source_windows'].append(href)
        row['source_commit'] = source_commit
        row['fingerprint'] = digest({**row, 'child_fingerprints': [by_id[c]['fingerprint'] for c in row['children']],
                                     'policy': {k: options[k] for k in ('thresholds', 'signals')}, 'version': 1})
        row['status'] = 'unreviewed'
        row['reason'] = options['deferred_pages'].get(page, 'No current item review; candidate heuristics are not acceptance')
        row['source_windows'] = []
        row['unreviewed_scope'] = ['Meaning, visualization suitability and source grounding have not been reviewed']
    return rows


def inspect_site(root, options, *, manifest=None, source_commit=''):
    """The manifest is authoritative when supplied; staging uses every HTML file."""
    from .site_build import owned_path
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
    from .site_build import owned_path
    if REPORT not in manifest['outputs']:
        return
    recorded = json.loads(owned_path(root, REPORT).read_bytes())
    report = inspect_site(root, recorded['policy'], manifest=manifest, source_commit=recorded['source_commit'])
    records = {r['id']: {**r, 'figures': r.get('reviewed_figures', [])} for r in recorded['items']}
    if set(records) != {r['id'] for r in report['items']}:
        raise ValueError('Published visualization item set changed')
    enforce(apply_reviews(report, dict(schema=1, items=records)))


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
                          _html_path(rel), options, source_commit=commit)
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
