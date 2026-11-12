"""Prove that source dependencies survived a visualization review's revision change."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import PurePosixPath
import re
import subprocess
from urllib.parse import quote, unquote, urlsplit

from .document_metadata import split_frontmatter
from .site_paths import owned_path
from .source_links import source_link_template


_UNVERIFIED = '#sdd-unverified-source-comparison'


def valid_path(name):
    if not isinstance(name, str) or not name or any(c in name for c in '\\:\0\r\n'):
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and '..' not in path.parts and path.as_posix() == name


class SourceProof:
    def __init__(self, root, settings, previous_commit, current_commit):
        self.root = root
        self.previous_commit = previous_commit
        self.current_commit = current_commit
        self.trees, self.blobs, self.checked = {}, {}, {}
        self._tree(previous_commit)
        self._tree(current_commit)
        base = settings.source_url.rstrip('/')
        parts = urlsplit(base)
        if parts.scheme not in {'https', 'http'} or not parts.netloc or parts.query or parts.fragment:
            raise ValueError('Source revision reuse requires a configured HTTP repository URL')
        template = source_link_template(settings)
        fields = ('SDDREVISIONMARKER', 'SDDFILEMARKER', 91827364)
        literal = template.format(url=base, commit=fields[0], file=fields[1], line=fields[2])
        target = urlsplit(literal)
        if ((target.scheme, target.netloc) != (parts.scheme, parts.netloc)
                or any(literal.count(str(value)) != 1 for value in fields)):
            raise ValueError('Source revision reuse requires a literal commit, file and line in source links')
        self.link_prefix = literal.split(fields[0], 1)[0]
        self.links = re.compile(re.escape(literal)
            .replace(fields[0], '(?P<commit>[0-9a-f]{40})')
            .replace(fields[1], r'(?P<file>[^?#\s]+)')
            .replace(str(fields[2]), '(?P<line>[1-9][0-9]*)'))

    def _git(self, *args):
        result = subprocess.run(['git', '--no-replace-objects', *args], cwd=self.root, capture_output=True)
        if result.returncode:
            raise ValueError(f'Cannot read immutable Git source for visualization reuse: {args[0]}')
        return result.stdout

    def _tree(self, commit):
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('Visualization reuse requires full immutable Git commits')
        if commit not in self.trees:
            if self._git('cat-file', '-t', commit).strip() != b'commit':
                raise ValueError('Visualization source revision is not a Git commit')
            entries = {}
            for entry in self._git('ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
                if entry:
                    info, name = entry.split(b'\t', 1)
                    mode, kind, object_id = info.decode('ascii').split()
                    if kind == 'blob' and mode in {'100644', '100755'}:
                        entries[name] = mode, object_id
            self.trees[commit] = entries
        return self.trees[commit]

    def _same_file(self, name, commit):
        if not valid_path(name):
            return None
        original = self._tree(commit).get(name.encode('utf-8'))
        if original is None or original != self._tree(self.current_commit).get(name.encode('utf-8')):
            return None
        _, object_id = original
        if object_id not in self.blobs:
            raw = self._git('cat-file', 'blob', object_id)
            self.blobs[object_id] = raw.splitlines(keepends=True), hashlib.sha256(raw).hexdigest()
        lines, checksum = self.blobs[object_id]
        self.checked[(commit, name)] = checksum
        return lines, checksum

    def _link(self, href, commit):
        if _UNVERIFIED in href:
            raise ValueError('Reserved source comparison marker in visualization input')
        match = self.links.fullmatch(href)
        if match is None:
            if href.startswith(self.link_prefix) and commit == self.current_commit:
                return href + _UNVERIFIED
            return href
        name = unquote(match['file'])
        previous = self.previous_commit if match['commit'] == self.current_commit else match['commit']
        try:
            same = self._same_file(name, previous) if quote(name, safe='/') == match['file'] else None
        except ValueError:
            same = None
        if same and int(match['line']) <= len(same[0]):
            start, end = match.span('commit')
            return href[:start] + previous + href[end:]
        # Even if both snapshots retain a link to the old revision, a changed
        # file is not evidence for carrying the judgment to the current one.
        return href + _UNVERIFIED if commit == self.current_commit else href

    def normalize(self, document, commit, page, root):
        from .visual_audit import Node, digest, source_window

        for link in document.root.all('a'):
            if 'href' in link.attrs:
                link.attrs['href'] = self._link(link.attrs['href'], commit)
        # Paragraph-level citations are serialized as generated HTML in JSON.
        # Keep the citation label and markup and compare only the verified URL.
        local_windows, paragraphs = {}, {}
        for node in document.root.all('p'):
            value = node.attrs.get('data-sdd-evidence')
            if value is None:
                continue
            if _UNVERIFIED in value:
                raise ValueError('Reserved source comparison marker in visualization input')
            try:
                entries = json.loads(value)
                if not isinstance(entries, list):
                    raise ValueError('Invalid generated citations')
                normalized = []
                for label, anchor in entries:
                    citation = re.fullmatch(r'(<a(?: class="citation")? href=")([^"]+)("><code>[^<]+</code></a>)', anchor)
                    if citation is None or not isinstance(label, str):
                        raise ValueError('Unrecognized generated citation')
                    href = html.unescape(citation[2])
                    if re.fullmatch(r'#source-[0-9a-f]{16}', href):
                        if href not in local_windows:
                            local_windows[href] = digest(source_window(document, href[1:], root=root, page=page, presentation=True))
                        normalized.append([label, anchor, local_windows[href]])
                    else:
                        target = self._link(href, commit)
                        normalized.append([label, anchor if target == href else
                                           citation[1] + html.escape(target, quote=True) + citation[3]])
                paragraphs[id(node)] = json.dumps(normalized, ensure_ascii=False)
            except (ValueError, TypeError):
                if commit == self.current_commit:
                    paragraphs[id(node)] = value + _UNVERIFIED
        for node in document.root.all('p'):
            if id(node) in paragraphs:
                node.attrs['data-sdd-evidence'] = paragraphs[id(node)]
        # The renderer emits the current revision as a single code cell in
        # generated provenance. Keep historic revisions and arbitrary prose.
        mains = list(document.root.all('main'))
        sections = [node for node in mains[0].children if isinstance(node, Node) and node.tag == 'section'] if len(mains) == 1 else []
        for section in sections:
            elements = [child for child in section.children if isinstance(child, Node)]
            if (section.attrs.get('class') != 'evidence' or not elements or elements[0].tag != 'h2'
                    or elements[0].attrs.get('id') != 'page-evidence'):
                continue
            for dl in (node for node in elements if node.tag == 'dl'):
                cells = [child for child in dl.children if isinstance(child, Node)]
                for label, value in zip(cells, cells[1:]):
                    if (label.tag == 'dt' and label.children in [['분석 기준 커밋'], ['Analysis baseline commit']]
                            and value.tag == 'dd' and len(value.children) == 1):
                        code = value.children[0]
                        if isinstance(code, Node) and code.tag == 'code' and code.children == [commit]:
                            code.children = [self.previous_commit]

    def additional_sources_unchanged(self, record):
        windows = record.get('additional_source_windows', [])
        manifest = record.get('additional_source_manifest', {})
        if not isinstance(windows, list) or not isinstance(manifest, dict) or any(
                not isinstance(window, str) or window not in manifest for window in windows):
            return False
        for key, value in manifest.items():
            if not isinstance(value, dict):
                return False
            commit, name = value.get('source_commit'), value.get('file')
            first, last = value.get('first_line'), value.get('last_line')
            if (not valid_path(name) or not isinstance(commit, str) or
                    key not in {f'git:{commit}:{name}', f'git:{commit}:{name}#L{first}-L{last}'}):
                return False
            try:
                same = self._same_file(name, commit)
            except ValueError:
                return False
            if not same or type(first) is not int or type(last) is not int:
                return False
            lines, checksum = same
            if not 1 <= first <= last <= len(lines) or value.get('file_sha256', checksum) != checksum:
                return False
            if hashlib.sha256(b''.join(lines[first-1:last])).hexdigest() != value.get('sha256'):
                return False
        return True


def trace_proof(record, baseline, current, page, previous_commit, current_commit):
    trace = record.get('trace_evidence')
    if trace is None:
        return {}
    name = page.removeprefix('en/').removesuffix('.html') + '.md'
    before, after = (owned_path(root, name) for root in (baseline, current))
    if not isinstance(trace, dict) or not before.is_file() or not after.is_file():
        return None
    raw = before.read_bytes()
    previous_proof = record.get('source_reuse', {})
    expected = (trace.get('manuscript_sha256') if trace.get('source_commit') == previous_commit else
                previous_proof.get('trace_manuscript_sha256') if previous_proof.get('current_commit') == previous_commit else None)
    if expected != hashlib.sha256(raw).hexdigest():
        return None
    current_raw = after.read_bytes()
    old, old_body = split_frontmatter(raw.decode('utf-8'))
    new, new_body = split_frontmatter(current_raw.decode('utf-8'))
    pin = trace.get('scenario_fingerprint')
    if not (bool(pin) and pin == old.get('scenario_fingerprint') == new.get('scenario_fingerprint')
            and old.get('source_commit') == previous_commit and new.get('source_commit') == current_commit
            and old_body == new_body):
        return None
    return {'trace_manuscript_sha256': hashlib.sha256(current_raw).hexdigest()}
