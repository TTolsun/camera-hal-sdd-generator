"""Offline English editions from exact, reviewed display-text catalogs.

Translate display text only: identifiers, citations, code and link anchors stay
intact. Missing text or stale page hashes abort the staged build.
"""
from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

KOREAN = re.compile(r"[가-힣]")
ATTRIBUTES = {"aria-label", "placeholder", "title"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def english_diagram(source: str) -> str:
    """Translate only generator-owned edge labels, never nodes or edges."""
    labels = {'상속': 'inheritance', '필드 참조': 'field reference', '의존': 'dependency',
              '집합': 'aggregation', '합성': 'composition'}
    for ko, en in labels.items():
        source = source.replace('|' + ko + '|', '|' + en + '|')
    return source.replace(' · virtual 후보"|', ' · virtual candidate"|').replace(
        ' · 예약된 호출, 실행 순서는 정적으로 확인 불가"|',
        ' · dispatched method; execution order not established statically"|')


class DisplayText(HTMLParser):
    def __init__(self, translate):
        super().__init__(convert_charrefs=True)
        self.translate = translate
        self.tree = {'raw': '', 'end': '', 'children': [], 'protected': False, 'attrs': []}
        self.stack = [self.tree]

    @property
    def output(self):
        def render(node):
            if isinstance(node, str):
                return html.escape(node, quote=False)
            children = node['children']
            raw = node['raw']
            if node['protected']:
                if node.get('tag') in {'script', 'style'}:
                    return raw + ''.join(children) + node['end']
                if node.get('mermaid'):
                    return raw + html.escape(english_diagram(''.join(children)), quote=False) + node['end']
                return raw + ''.join(render(c) for c in children) + node['end']
            for name, value in node['attrs']:
                if name in ATTRIBUTES and value:
                    translated = self.translate(value)
                    raw = re.sub(rf'({name}\s*=\s*)([\"\']).*?\2',
                                 lambda m: m[1] + '"' + html.escape(translated, quote=True) + '"', raw)
            rendered = [render(c) for c in children]
            # Inline elements become opaque placeholders, so translators can move
            # code identifiers and links to natural English sentence positions.
            if any(isinstance(c, str) and KOREAN.search(c) for c in children):
                tokens = {f'{{{{{i}}}}}': value for i, (c, value) in enumerate(zip(children, rendered)) if not isinstance(c, str)}
                text = ''.join(c if isinstance(c, str) else f'{{{{{i}}}}}' for i, c in enumerate(children))
                translated = self.translate(text)
                if sorted(re.findall(r'\{\{\d+\}\}', translated)) != sorted(tokens):
                    raise RuntimeError('English translation changed inline placeholders')
                body = html.escape(translated, quote=False)
                body = re.sub(r'\{\{\d+\}\}', lambda m: tokens[m[0]], body)
            else:
                body = ''.join(rendered)
            return raw + body + node['end']
        return [render(self.tree)]

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        protected = self.stack[-1]['protected'] or tag in {"pre", "code", "script", "style"}
        protected |= "mermaid" in (values.get("class") or "").split()
        node = {'raw': self.get_starttag_text(), 'end': '', 'children': [], 'protected': protected, 'attrs': attrs, 'tag': tag,
                'mermaid': 'mermaid' in (values.get('class') or '').split()}
        self.stack[-1]['children'].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if len(self.stack) > 1 and self.stack[-1]['tag'] == tag:
            self.stack.pop()['end'] = f'</{tag}>'

    def handle_data(self, data):
        self.stack[-1]['children'].append(data)

    def handle_comment(self, data):
        self.stack[-1]['children'].append({'raw': f'<!--{data}-->', 'end': '', 'children': [], 'protected': True, 'attrs': []})

    def handle_decl(self, decl):
        self.stack[-1]['children'].append({'raw': f'<!{decl}>', 'end': '', 'children': [], 'protected': True, 'attrs': []})


def display_strings(document: str) -> list[str]:
    """Collect translatable units for authoring a catalog without an LLM service."""
    found = set()
    def collect(value):
        if KOREAN.search(value):
            found.add(value.strip())
        return value
    parser = DisplayText(collect)
    parser.feed(document)
    parser.output
    return sorted(found)


def source_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def selector(document: str, rel: str, english: bool) -> str:
    current = "en/" + rel if english else rel
    ko = posixpath.relpath(rel, posixpath.dirname(current) or ".")
    en = posixpath.relpath("en/" + rel, posixpath.dirname(current) or ".")
    links = ''.join(f'<a lang="{lang}" hreflang="{lang}" href="{html.escape(href, quote=True)}"'
                    + (' aria-current="true"' if selected else '') + f'>{label}</a>'
                    for lang, href, label, selected in [('ko', ko, '한국어', not english), ('en', en, 'English', english)])
    control = ('<details class="language-selector"><summary aria-label="'
               + ('Choose language' if english else '언어 선택') + '">'
               + ('English' if english else '한국어') + ' ▾</summary><nav>' + links + '</nav></details>')
    alternates = ''.join(f'<link rel="alternate" hreflang="{lang}" href="{html.escape(href, quote=True)}">'
                         for lang, href in [('ko', ko), ('en', en)])
    return document.replace('<div class="header-actions">', '<div class="header-actions">' + control, 1).replace('</head>', alternates + '</head>', 1)


def localize_site(cfg, out: Path) -> None:
    catalog_path = (cfg.raw.get('site') or {}).get('english_catalog')
    if not catalog_path:
        return
    if (cfg.raw.get('site') or {}).get('require_approval'):
        raise RuntimeError('English translations have no human approval ledger; site.require_approval blocks publication')
    catalog = json.loads((cfg.root / catalog_path).read_text(encoding='utf-8'))
    if catalog.get('schema') != 1 or not isinstance(catalog.get('strings'), dict):
        raise RuntimeError('Invalid English catalog schema')
    strings = catalog['strings']
    def translate(value):
        key = value.strip()
        if not KOREAN.search(key):
            return value
        translated = strings.get(key)
        if not isinstance(translated, str) or not translated.strip() or KOREAN.search(translated):
            raise RuntimeError(f'English translation missing: {key[:160]}')
        return value[:len(value) - len(value.lstrip())] + translated + value[len(value.rstrip()):]

    pages = sorted(out.rglob('*.html'))
    if any(p.relative_to(out).parts[0] == 'en' for p in pages):
        raise RuntimeError('The en/ path is reserved for English editions')
    expected = {p.relative_to(out).as_posix(): source_hash(p.read_text(encoding='utf-8')) for p in pages}
    if catalog.get('pages') != expected:
        raise RuntimeError('English catalog source hashes changed; review translations before publishing')
    for path in pages:
        rel = path.relative_to(out).as_posix()
        original = path.read_text(encoding='utf-8')
        parser = DisplayText(translate)
        parser.feed(original)
        english = ''.join(parser.output).replace('<html lang="ko">', '<html lang="en">', 1)
        # English HTML routes retain their relative structure. Assets and original
        # downloads remain shared with Korean pages, including local Mermaid chunks.
        def shared(match):
            attr, value = match[1], html.unescape(match[2])
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path or parts.path.endswith(('.html', '.mmd')):
                return match[0]
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), parts.path))
            href = posixpath.relpath(target, posixpath.dirname('en/' + rel))
            if parts.query:
                href += '?' + parts.query
            if parts.fragment:
                href += '#' + parts.fragment
            return f'{attr}="{html.escape(href, quote=True)}"'
        english = re.sub(r'(href|src)="([^"]+)"', shared, english)
        def config(match):
            data = json.loads(match[1])
            data['language'] = 'en'
            if not urlsplit(data['mermaid']).scheme and not data['mermaid'].startswith('/'):
                data['mermaid'] = '../' + data['mermaid']
            return '<script id="site-config" type="application/json">' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
        english = re.sub(r'<script id="site-config" type="application/json">(.*?)</script>', config, english, flags=re.S)
        english = english.replace('<article>', '<p class="translation-note">English translation · human review pending. Review states below refer to the Korean source.</p><article>', 1)
        dest = out / 'en' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(selector(english, rel, True), encoding='utf-8', newline='\n')
        path.write_text(selector(original, rel, False), encoding='utf-8', newline='\n')
    search = json.loads((out / 'assets/search.json').read_text(encoding='utf-8'))
    for entry in search:
        entry['title'] = translate(entry['title'])
        entry['page'] = translate(entry['page'])
    dest = out / 'en/assets/search.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(search, ensure_ascii=False), encoding='utf-8')
    for source in sorted(out.rglob('*.mmd')):
        dest = out / 'en' / source.relative_to(out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(english_diagram(source.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')


def main() -> None:
    """Explicit catalog refresh; new strings remain empty until translated."""
    import argparse
    import copy
    import tempfile
    from .config import load
    from .export_site import _render_site
    parser = argparse.ArgumentParser(description='Prepare an English catalog for translation review')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = copy.deepcopy(load(args.config))
    cfg.raw.setdefault('site', {}).pop('english_catalog', None)
    previous = json.loads(args.out.read_text(encoding='utf-8')) if args.out.exists() else {}
    cfg.build_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.translation-', dir=cfg.build_dir) as temporary:
        out = _render_site(cfg, Path(temporary))
        pages, units = {}, set()
        for path in sorted(out.rglob('*.html')):
            document = path.read_text(encoding='utf-8')
            pages[path.relative_to(out).as_posix()] = source_hash(document)
            units.update(display_strings(document))
        for entry in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
            units.update(entry[k].strip() for k in ('title', 'page') if KOREAN.search(entry[k]))
    catalog = {'schema': 1, 'review_status': 'human-review-pending', 'pages': pages,
               'strings': {key: previous.get('strings', {}).get(key, '') for key in sorted(units)}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(pages)} pages and {len(units)} strings. Review all changed source context before publishing.')


if __name__ == '__main__':
    main()
