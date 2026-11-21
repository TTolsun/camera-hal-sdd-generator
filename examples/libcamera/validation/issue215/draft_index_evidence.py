"""Verify generated index rows against pinned facts and immutable file positions."""
import hashlib
from io import BytesIO
import re
import subprocess

import markdown

from sdd.site_paths import owned_path
from sdd.visual_audit import Document, Node, digest, plain


HEADERS = {
    ('클래스', '선언 위치', '상속', '책임 (주석)'): 'classes',
    ('함수', '선언 위치', '정의 위치', '설명 (주석)'): 'functions',
}


def table_rows(table, tag):
    return [tuple(plain(cell) for cell in row.all(tag)) for row in table.all('tr') if list(row.all(tag))]


def location(value, missing):
    return f"{value['file']}:{value['line']}" if value else missing


def package_tables(article):
    tables = {}
    owner = None
    for node in article.children:
        if not isinstance(node, Node):
            continue
        if re.fullmatch(r'h[1-6]', node.tag):
            owner = node.attrs.get('id')
        elif node.tag == 'table' or 'table-scroll' in node.attrs.get('class', '').split():
            if not owner:
                raise ValueError('Source index table has no package anchor')
            tables.setdefault(owner, []).extend([node] if node.tag == 'table' else node.all('table'))
    return tables


def git_blobs(source, commit, names):
    names = sorted(names)
    for name in names:
        owned_path(source, name)
        if '\n' in name or '\r' in name:
            raise ValueError('Source index path contains a line break')
    requests = ''.join(f'{commit}:./{name}\n' for name in names).encode()
    result = BytesIO(subprocess.check_output(['git', 'cat-file', '--batch'], input=requests, cwd=source))
    blobs = {}
    for name in names:
        match = re.fullmatch(rb'[0-9a-f]+ blob ([0-9]+)\n', result.readline())
        if not match:
            raise ValueError('Source index file is not a blob at the pinned commit: '+name)
        size = int(match[1])
        raw = result.read(size)
        if len(raw) != size or result.read(1) != b'\n':
            raise ValueError('Incomplete pinned source blob: '+name)
        blobs[name] = (raw.splitlines(), hashlib.sha256(raw).hexdigest())
    if result.read(1):
        raise ValueError('Unexpected objects after pinned source blobs')
    return blobs


def verify_index(html, page, facts, source, source_commit):
    """Bind each displayed cell and source location before the editorial call."""
    article, = Document(html).root.all('article')
    packages = {}
    files = set()
    for anchor, tables in package_tables(article).items():
        checked = []
        for table in tables:
            header, = table_rows(table, 'th')
            kind = HEADERS.get(header)
            if not kind:
                raise ValueError('Unknown extracted-index table shape: '+str(header))
            for values in table_rows(table, 'td'):
                name, first, third, comment = values
                fact = facts[kind].get(name)
                if fact is None:
                    raise ValueError('Source index row has no matching extracted symbol: '+name)
                declaration = fact.get('loc')
                definition = fact.get('def_loc') if kind == 'functions' else None
                expected_first = location(declaration, '위치 없음' if kind == 'classes' else '–')
                expected_third = (', '.join(fact.get('bases', [])) or '–' if kind == 'classes'
                                  else location(definition, '–'))
                brief = fact.get('brief') or '확인 필요'
                rendered = markdown.markdown(f'| comment |\n|---|\n| {brief} |', extensions=['tables'])
                expected_comment = plain(next(Document(rendered).root.all('td')))
                if (first, third, comment) != (expected_first, expected_third, expected_comment):
                    raise ValueError('Source index row differs from extracted facts: '+name)
                checked.append([kind, name, declaration, definition])
                files.update(value['file'] for value in (declaration, definition) if value)
        packages[page+'#'+anchor] = checked
    if not packages:
        raise ValueError('No extracted index package tables were verified')
    blobs = git_blobs(source, source_commit, files)

    def verify_location(value):
        if value is None:
            return None
        name, line = value['file'], value['line']
        lines, _ = blobs[name]
        if type(line) is not int or not 0 < line <= len(lines):
            raise ValueError('Source index position is outside the pinned file: '+location(value, ''))
        return [name, line, hashlib.sha256(lines[line - 1]).hexdigest()]

    for key, rows in packages.items():
        checked = [[kind, name, verify_location(first), verify_location(last)]
                   for kind, name, first, last in rows]
        packages[key] = {'rows': checked, 'sha256': digest(checked)}
    return {'source_commit': source_commit, 'packages': packages,
            'blob_sha256': {name: value[1] for name, value in blobs.items()}}
