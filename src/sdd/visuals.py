"""Question-specific diagrams bound to pinned source excerpts, never inferred calls.

The graph is an authored interpretation. Pins and quotes detect drift; they do
not establish semantic correctness or confer human approval.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from pathlib import PurePosixPath

import yaml

from .config import section_output


class StaleVisualEvidence(ValueError):
    """A well-formed authored diagram no longer matches current source text."""


def definitions(cfg, section):
    settings = cfg.visuals
    if not settings.file:
        return []
    path = cfg.root / settings.file
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('sections'), dict):
        raise ValueError('Invalid visuals schema')
    unknown = set(data['sections']) - {s['id'] for s in cfg.sections()}
    if unknown:
        raise ValueError(f'Unknown visual sections: {sorted(unknown)}')
    values = data['sections'].get(section['id'], [])
    if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
        raise ValueError('Visuals must be an object list')
    return values


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\r\n'):
        raise ValueError(f'Visual {field} must be a nonempty single line')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', value):
        raise ValueError('Visual IDs must be lowercase identifiers')
    return value


def wrap_label(value, width=28):
    """Keep every character, wrapping Korean/Latin labels before escaping HTML."""
    def size(text):
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)
    lines, line = [], ''
    for word in re.findall(r'\S+\s*|\s+', value):
        if line and size(line + word) > width:
            lines.append(line)
            line = ''
        for char in word:
            if line and size(line + char) > width:
                lines.append(line)
                line = ''
            line += char
    if line:
        lines.append(line)
    return '<br/>'.join(html.escape(part, quote=True) for part in lines)


def _records(model, section, item):
    refs = item.get('evidence')
    if not isinstance(refs, list) or not refs or any(not isinstance(r, dict) for r in refs):
        raise ValueError('Every visual node and edge needs evidence')
    records, stale = [], []
    sources = {f"{t['id']}/{s['id']}": s for t in section.get('design_topics', []) for s in t.get('sources', [])}
    for ref in refs:
        if set(ref) != {'source', 'sha256', 'quote'} or not isinstance(ref.get('source'), str):
            raise ValueError('Visual evidence requires source, sha256 and quote')
        record = model.evidence.get(f"{section['id']}/{ref['source']}", {})
        text = record.get('text', '')
        quote = ref['quote']
        if (record.get('status') != 'available' or record.get('commit') != model.meta.get('source_commit')
                or not re.fullmatch(r'[0-9a-f]{40}', str(record.get('commit', '')))
                or record.get('selector') != sources.get(ref['source'])
                or ref['source'] not in sources
                or hashlib.sha256(text.encode()).hexdigest() != record.get('sha256')
                or not isinstance(quote, str) or not quote.strip()
                or not isinstance(ref['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', ref['sha256'])):
            raise ValueError(f"Visual evidence changed or quote is not unique: {section['id']}/{ref['source']}")
        if record.get('sha256') != ref['sha256'] or text.count(quote) != 1:
            stale.append(f"{section['id']}/{ref['source']}")
        records.append(record)
    if stale:
        raise StaleVisualEvidence('Visual evidence changed or quote is not unique: ' + ', '.join(stale))
    return records


def render(cfg, model, section):
    """Return validated (definition, Markdown, Mermaid) tuples."""
    values = definitions(cfg, section)
    return render_values(cfg, model, section, values)


def render_values(cfg, model, section, values):
    if not values:
        return []
    if model is None:
        raise ValueError('facts.json is required for question visuals')
    if section.get('kind', 'prose') != 'prose' or not section.get('show_evidence'):
        raise ValueError('Question visuals require prose and show_evidence')
    limit = cfg.visuals.max_nodes
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError('Invalid visuals.max_nodes')
    topics = {t['id']: t for t in section.get('design_topics', [])}
    titles = [t.get('title') for t in section.get('design_topics', [])]
    seen, result = set(), []
    for visual in values:
        ident = _id(visual.get('id'))
        if ident in seen:
            raise ValueError('Duplicate visual ID')
        seen.add(ident)
        if set(visual) - {'id', 'topic', 'kind', 'title', 'question', 'nodes', 'edges', 'producer', 'condition_display'}:
            raise ValueError('Unknown visual setting')
        if visual.get('condition_display','inline') not in ('inline','evidence'):
            raise ValueError('Visual condition_display must be inline or evidence')
        if visual.get('kind') not in {'state', 'flow', 'ownership', 'decision'} or visual.get('topic') not in topics:
            raise ValueError('Visual kind or topic is invalid')
        if titles.count(topics[visual['topic']].get('title')) != 1:
            raise ValueError('Visual target heading must be unique')
        title, question = (_text(visual.get(k), k) for k in ('title', 'question'))
        nodes, edges = visual.get('nodes'), visual.get('edges')
        if not isinstance(nodes, list) or not nodes or any(not isinstance(n, dict) for n in nodes):
            raise ValueError('Visual nodes must be a nonempty object list')
        if not isinstance(edges, list) or not edges or any(not isinstance(e, dict) for e in edges):
            raise ValueError('Visual edges must be a nonempty object list')
        if len(nodes) > limit:
            raise ValueError(f'Visual {ident} has {len(nodes)} nodes (limit {limit}); split the diagram')
        ids, translations, rows, proof = set(), {}, ['flowchart TB'], []
        stale = []
        def label(item):
            def display(value):
                # Only a source-verified, generator-added guard suffix may be
                # shortened. Full conditions remain in the evidence table.
                match = re.fullmatch(r'(.*) · (.+) \[(true|false)\]',value)
                quotes=''.join(''.join(e.get('quote','').split()) for e in item.get('evidence',[]))
                if (visual.get('condition_display')=='evidence' and match
                        and ''.join(match[2].split()) in quotes):
                    return match[1]+' ['+match[3]+']'
                return value
            ko = wrap_label(display(_text(item.get('label'), 'label')))
            en = wrap_label(display(_text(item.get('label_en'), 'label_en')))
            if ko in translations and translations[ko] != en:
                raise ValueError('Conflicting visual label translations')
            translations[ko] = en
            return ko
        def evidence(item, name):
            try:
                records = _records(model, section, item)
            except StaleVisualEvidence as exc:
                if cfg.visuals.on_stale != 'omit':
                    raise
                stale.append(str(exc))
                return
            links = []
            for record in records:
                key = f"{record['file']}:{record['line']}:{record['sha256']}"
                anchor = hashlib.sha256(key.encode()).hexdigest()[:16]
                links.append(f"[{record['file']}:{record['line']}](#source-{anchor})")
            proof.append(f"| {html.escape(name).replace('|', '&#124;')} | {' · '.join(dict.fromkeys(links))} |")
        for node in nodes:
            if set(node) - {'id', 'label', 'label_en', 'shape', 'evidence'}:
                raise ValueError('Unknown visual node setting')
            nid = _id(node.get('id'))
            if nid in ids or node.get('shape', 'box') not in {'box', 'decision'}:
                raise ValueError('Duplicate visual node or invalid shape')
            ids.add(nid)
            text = label(node)
            shape = '{"' + text + '"}' if node.get('shape') == 'decision' else '["' + text + '"]'
            rows.append(f'  v_{nid}{shape}')
            evidence(node, node['label'])
        for edge in edges:
            if set(edge) - {'from', 'to', 'label', 'label_en', 'evidence'}:
                raise ValueError('Unknown visual edge setting')
            if _id(edge.get('from')) not in ids or _id(edge.get('to')) not in ids:
                raise ValueError('Visual edge references an unknown node')
            rows.append(f'  v_{edge["from"]} -->|"{label(edge)}"| v_{edge["to"]}')
            evidence(edge, edge['label'])
        if stale:
            # Validate all nodes and edges above, even after the first stale pin.
            # Do not emit the old interpretation, its links, or a Mermaid file.
            block = (f'<!-- sdd:visual:{ident} -->\n### {title}\n\n'
                     '소스 근거가 달라져 이 질문의 그림을 제외했습니다. 그림은 재검토가 필요합니다. '
                     '현재 설명과 소스 근거를 확인하세요.\n'
                     f'<!-- /sdd:visual:{ident} -->')
            result.append((visual, block, ''))
            continue
        rows.insert(1, '%% sdd:translations ' + json.dumps(translations, ensure_ascii=False, sort_keys=True))
        source = '\n'.join(rows)
        proof = ['| 요소·전이 | 소스 근거 |', '|---|---|'] + proof
        metadata = [question, '', '소스에 연결한 설계 해석입니다. 자동 연결 검사는 의미 승인이나 기기 실행 검증이 아닙니다.']
        if visual.get('producer'):
            producer = _text(visual['producer'], 'producer')
            metadata += ['', 'LLM 그림 초안 · 사람 검토 전', '', '작성 모델: `' + html.escape(producer) + '`']
        note = '??? note "그림 근거와 확인 범위"\n' + '\n'.join('    ' + line for line in [*metadata, '', *proof])
        download = PurePosixPath(section_output(section)).stem + '.' + ident + '.mmd'
        block = (f'<!-- sdd:visual:{ident} -->\n### {title}\n\n'
                 f'```mermaid\n{source}\n```\n\n[Mermaid 원문]({download})\n\n{note}\n<!-- /sdd:visual:{ident} -->')
        result.append((visual, block, source))
    return result


def strip_blocks(body):
    return re.sub(r'<!-- sdd:visual:([a-z][a-z0-9_-]*) -->.*?<!-- /sdd:visual:\1 -->\s*', '', body, flags=re.S)


def place(body, rendered, section):
    """Replace owned blocks and insert after the topic's first explanation."""
    body = strip_blocks(body)
    topics = {t['id']: t for t in section.get('design_topics', [])}
    grouped = {}
    for visual, block, _ in rendered:
        grouped.setdefault(visual['topic'], []).append(block)
    for tid, blocks in grouped.items():
        heading = '## ' + topics[tid]['title']
        matches = list(re.finditer(r'^' + re.escape(heading) + r'\n+', body, re.M))
        if len(matches) != 1:
            raise ValueError(f'Visual target heading missing or ambiguous: {heading}')
        start = matches[0].end()
        from .product_context import scope_notice
        notice = scope_notice(topics[tid])
        if notice and body.startswith(notice,start):
            start += len(notice)
        end = re.search(r'\n\n|\n(?=## )', body[start:])
        if end is None or not body[start:start + end.start()].strip():
            raise ValueError(f'Visual target has no explanation: {heading}')
        # An inserted heading splits an ordered list and resets its numbering.
        # Keep procedures intact by putting their diagram before the first step.
        position = start if re.match(r'(?:\d+\. |[-*+] )', body[start:]) else start + end.start()
        insertion = '\n\n'.join(blocks)
        if position == start:
            body = body[:position] + insertion + '\n\n' + body[position:]
        else:
            body = body[:position] + '\n\n' + insertion + body[position:]
    return body
