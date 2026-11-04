"""Question diagrams pinned to a project's introductory reading guide.

These are document navigation, not claims about the analyzed program. Reuse the
normal visual renderer, node limits, bilingual labels and accessible downloads,
with a separate guide identity and a local copy of the actual guide evidence.
"""
from __future__ import annotations

import hashlib
import html
import re
import subprocess
from html.parser import HTMLParser

from .facts.model import KnowledgeModel
from .visuals import place, render_values
from .validation_stage import load_json, read_bytes
from .site_paths import owned_path


def headings(body):
    """Locate actual top-level ATX H2s using the production Markdown parser."""
    matches = list(re.finditer(r'^## ([^\n]+)\n+', body, re.M))
    prefix = 'sdd-guide-heading-'+hashlib.sha256(body.encode()).hexdigest()+'-'
    index = iter(range(len(matches)))
    marked = re.sub(r'^## ([^\n]+)\n+', lambda m: m[0].replace('\n',
        '<span data-sdd-guide-probe="'+prefix+str(next(index))+'"></span>\n',1), body, flags=re.M)
    from .site_markdown import _render
    rendered, _, _ = _render(marked,'index.md',{'index.md'},None,'','')
    class Probes(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_h2, self.code_depth, self.found = False, 0, set()
        def handle_starttag(self, tag, attrs):
            if tag in {'pre','code'}:
                self.code_depth += 1
            if tag == 'h2' and not self.code_depth:
                self.in_h2 = True
            value = dict(attrs).get('data-sdd-guide-probe','')
            if tag == 'span' and self.in_h2 and not self.code_depth and value.startswith(prefix):
                self.found.add(int(value[len(prefix):]))
        def handle_endtag(self, tag):
            if tag == 'h2':
                self.in_h2 = False
            if tag in {'pre','code'}:
                self.code_depth = max(0,self.code_depth-1)
    probes = Probes()
    probes.feed(rendered)
    return [match for index,match in enumerate(matches) if index in probes.found]


def inject(cfg, body, existing_ids):
    path = cfg.site.guide_visuals
    if not path:
        return body, []
    data = load_json(cfg.root / path)
    if set(data) != {'schema', 'source', 'figures'} or data['schema'] != 1:
        raise ValueError('Invalid guide visual schema')
    source = data['source']
    if (not isinstance(source, dict) or set(source) != {'file', 'sha256', 'commit'}
            or not cfg.site.intro or source['file'] != cfg.site.intro
            or not re.fullmatch(r'[0-9a-f]{40}', str(source['commit']))):
        raise ValueError('Guide visuals require their separate introductory source identity')
    raw = read_bytes(cfg.root / source['file'])
    if hashlib.sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('Reading guide changed; regenerate and review its diagrams')
    text = raw.decode('utf-8')
    excerpt = text.replace('\r\n', '\n').replace('\r', '\n')
    origin = cfg.site.guide_source
    if (not isinstance(origin, dict) or set(origin) != {'root', 'file'}
            or any(not isinstance(v, str) or not v for v in origin.values())):
        raise ValueError('Guide provenance requires its separately configured repository and file')
    repository = (cfg.root / origin['root']).resolve()
    owned_path(repository, origin['file'])
    committed = subprocess.check_output(['git', 'show', source['commit']+':./'+origin['file']],
                                        cwd=repository, text=True, encoding='utf-8')
    if committed != excerpt:
        raise ValueError('Reading guide does not match its recorded source commit')
    sha = hashlib.sha256(excerpt.encode()).hexdigest()
    selector = dict(id='intro', file=source['file'])
    record = dict(status='available', commit=source['commit'], selector=selector,
                  file=source['file'], line=1, end_line=len(excerpt.splitlines()), text=excerpt, sha256=sha)
    model = KnowledgeModel(meta=dict(source_commit=source['commit']), evidence={'guide-navigation/guide/intro':record})
    figures = data['figures']
    if not isinstance(figures, list) or not figures:
        raise ValueError('Guide visual figures must be nonempty')
    ids, seen_headings, rendered = set(existing_ids), set(), []
    for item in figures:
        if not isinstance(item, dict) or set(item) != {'heading', 'visual'}:
            raise ValueError('Guide figure needs a heading and a normal visual definition')
        heading, visual = item['heading'], item['visual']
        if (not isinstance(heading, str) or not heading.strip() or '\n' in heading
                or heading in seen_headings or not isinstance(visual, dict)
                or visual.get('id') in ids or visual.get('topic') != 'guide'):
            raise ValueError('Guide visual headings and IDs must be unique')
        seen_headings.add(heading)
        ids.add(visual.get('id'))
        source_headings = headings(excerpt)
        original = [m for m in source_headings if m[1] == heading]
        if len(original) != 1:
            raise ValueError('Guide evidence heading is missing or ambiguous')
        stop = next((m.start() for m in source_headings if m.start() > original[0].start()),len(excerpt))
        source_window = excerpt[original[0].end():stop]
        section = dict(id='guide-navigation', kind='prose', output='index.md', show_evidence=True,
                       design_topics=[dict(id='guide', title=heading, sources=[selector])])
        # A local doc pin must fail closed even when ordinary stale visuals are
        # configured to be omitted. Never silently delete a required guide map.
        for element in [*visual.get('nodes', []), *visual.get('edges', [])]:
            if any(ref.get('source') != 'guide/intro' or ref.get('sha256') != sha
                   or not isinstance(ref.get('quote'), str) or source_window.count(ref['quote']) != 1
                   for ref in element.get('evidence', [])):
                raise ValueError('Guide diagram has stale or foreign evidence')
        values = render_values(cfg, model, section, [visual])
        if not values[0][2]:
            raise ValueError('Guide diagram cannot be omitted')
        body_headings = headings(body)
        matches = [m for m in body_headings if m[1] == heading]
        if len(matches) != 1:
            raise ValueError('Guide diagram heading is missing or ambiguous')
        start = matches[0].start()
        end = next((m.start() for m in body_headings if m.start() > start),len(body))
        if body[start:end].rstrip('\n') != excerpt[original[0].start():stop].rstrip('\n'):
            raise ValueError('Rendered guide question differs from its pinned introductory source')
        # Limit replacement to this question. Existing diagrams elsewhere and
        # complete numbered procedures retain their original positions.
        block = place(body[start:end], values, section)
        body = body[:start]+block+body[end:]
        rendered.extend(values)
    anchor = hashlib.sha256(f"{record['file']}:1:{sha}".encode()).hexdigest()[:16]
    # Match the existing reader-tools evidence anchor/panel contract so a
    # citation opens the original guide and offers a focus-preserving return.
    body += (f'\n\n<a id="source-{anchor}"></a>\n\n<details data-sdd-guide-source="true">\n'
             '<summary>독서 안내 원문과 검토 범위</summary>\n'
             '<p>프로젝트 문서의 읽기 경로입니다. 라이브러리의 실행 순서나 기기 검증을 뜻하지 않습니다. '
             f'안내 문서 커밋: <code>{source["commit"]}</code>; '
             f'원문 SHA-256: <code>{source["sha256"]}</code>.</p>\n'
             f'<pre><code>{html.escape(excerpt)}</code></pre>\n</details>\n')
    return body, rendered
