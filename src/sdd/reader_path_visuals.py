"""Local role-question figures using the normal pinned-source renderer."""
from pathlib import PurePosixPath
import posixpath
import re

from .config import section_output
from .validation_stage import load_yaml


def configuration(cfg, data=None):
    if not cfg.site.reader_paths:
        return None
    data = load_yaml(cfg.root / cfg.site.reader_paths) if data is None else data
    spec = data.get('visuals')
    if spec is None:
        return None
    from .reader_path_contract import _mapping, _text, _items
    _mapping(spec, {'file', 'placements'})
    _text(spec['file'], 'visual file')
    _items(spec['placements'], 'visual placements')
    return spec


def definition_file(cfg):
    spec = configuration(cfg)
    return cfg.root / spec['file'] if spec else None


def placements(cfg, data, sections):
    spec = configuration(cfg, data)
    if spec is None:
        return []
    from .reader_path_contract import _mapping, _id
    roles = {role['id']: role for role in data['roles']}
    claims = {claim['id']: claim for claim in data['claims']}
    available = {value['id'] for value in sections.values()}
    seen_targets, seen_graphs, seen_outputs, allowed = set(), set(), set(), {}
    for item in spec['placements']:
        _mapping(item, {'role', 'anchor', 'section', 'visual'})
        for key in item:
            _id(item[key])
        if item['role'] not in roles or item['section'] not in available:
            raise ValueError('Reader visual role or source section is missing')
        questions = roles[item['role']]['questions']
        used = {cid for question in questions for cid in question['claims']}
        anchors = {'question-'+question['aspect'] for question in questions} | {'claim-'+cid for cid in used}
        if item['anchor'] not in anchors:
            raise ValueError('Reader visual must answer a real role item with a referenced canonical source')
        if item['anchor'].startswith('claim-'):
            selected = [item['anchor'].removeprefix('claim-')]
        else:
            displayed = set()
            selected = []
            for question in questions:
                local = [cid for cid in question['claims'] if cid not in displayed]
                if 'question-'+question['aspect'] == item['anchor']:
                    selected = local[:1]
                    break
                displayed.update(question['claims'])
            if not selected:
                raise ValueError('Reader visual question needs a local claim explanation')
        refs = {(ref['section'], ref['topic']) for cid in selected
                for ref in [*claims[cid]['sources'], *claims[cid].get('details', [])]}
        if item['section'] not in {sid for sid, topic in refs}:
            raise ValueError('Reader visual must answer a real role item with a referenced canonical source')
        # Question anchors alias the first local claim; count that effective
        # item once even when configuration uses two different anchor spellings.
        target = item['role'], selected[0]
        graph = item['section'], item['visual']
        output = item['role'], item['visual']
        if output in seen_outputs:
            raise ValueError('Reader visual output IDs must be unique within a role')
        if target in seen_targets or graph in seen_graphs:
            raise ValueError('Reader visuals require one unique figure per placement; repeated figures cannot fill roles')
        seen_targets.add(target); seen_graphs.add(graph); seen_outputs.add(output)
        allowed[graph] = refs
    definitions = load_yaml(cfg.root / spec['file'])
    _mapping(definitions, {'schema', 'sections'})
    if type(definitions['schema']) is not int or definitions['schema'] != 1 or not isinstance(definitions['sections'], dict):
        raise ValueError('Invalid reader visual definitions')
    declared = set()
    for sid, values in definitions['sections'].items():
        if sid not in available or not isinstance(values, list):
            raise ValueError('Invalid reader visual source section')
        for value in values:
            if not isinstance(value, dict):
                raise ValueError('Reader visual definition must be an object')
            ident = _id(value.get('id'))
            if (sid, ident) in declared:
                raise ValueError('Duplicate reader visual definition')
            declared.add((sid, ident))
            refs = allowed.get((sid, ident), set())
            if (sid, value.get('topic')) not in refs:
                raise ValueError('Reader visual topic must be referenced by its target item')
            for field in ('nodes', 'edges'):
                elements = value.get(field)
                if not isinstance(elements, list) or any(not isinstance(e, dict) for e in elements):
                    raise ValueError('Reader visual nodes and edges must be object lists')
                for element in elements:
                    pins = element.get('evidence')
                    if not isinstance(pins, list) or any(not isinstance(p, dict) for p in pins):
                        raise ValueError('Reader visual evidence must be an object list')
                    for pin in pins:
                        source = pin.get('source', '')
                        if not isinstance(source, str) or (sid, source.split('/')[0]) not in refs:
                            raise ValueError('Reader visual evidence must belong to its target item references')
    if declared != seen_graphs:
        raise ValueError('Reader visual definitions and placements must match exactly')
    return spec['placements']


def _position(body, anchor):
    heading = re.compile(r'^(#{2,3}) [^\n]+ \{#'+re.escape(anchor)+r'\}\n+', re.M)
    matches = list(heading.finditer(body))
    if len(matches) != 1:
        raise ValueError('Reader visual target heading missing or ambiguous: '+anchor)
    match = matches[0]; level = len(match[1]); start = match.end()
    boundary = re.search(r'^#{1,'+str(level)+r'} ', body[start:], re.M)
    stop = start + boundary.start() if boundary else len(body)
    if anchor.startswith('question-'):
        claim = re.search(r'^### [^\n]+ \{#(claim-[a-z0-9-]+)\}\n', body[start:stop], re.M)
        if not claim:
            raise ValueError('Reader visual question needs an explanation in a local claim: '+anchor)
        # Use the displayed claim's explanation and heading depth, while the
        # source contract is restricted to that same first displayed claim.
        position, depth = _position(body[start+claim.start():stop], claim[1])
        return start + claim.start() + position, depth
    # Claim-kind labels are not the explanation that a figure should follow.
    from .reader_path_contract import KINDS
    fact = False
    for label in KINDS.values():
        prefix = '**'+label+'**\n\n'
        if body.startswith(prefix, start):
            start += len(prefix)
            fact = label == KINDS['fact']
            break
    if fact:
        # Scope warnings and detail links precede a fact's projected answer.
        # Preserve that order, then put the figure after the actual answer.
        quote = re.search(r'^> ', body[start:stop], re.M)
        if not quote:
            raise ValueError('Reader visual fact needs a projected explanation: '+anchor)
        start += quote.start()
    paragraph = re.search(r'\n\n|\n(?=##+ )', body[start:stop])
    end = start + paragraph.start() if paragraph else stop
    if not body[start:end].strip() or body[start:end].startswith('#'):
        raise ValueError('Reader visual target needs an explanation: '+anchor)
    # Keep numbered/bulleted procedures and indented continuations intact.
    def unquote(text):
        return re.sub(r'^(?:> ?)+', '', text)

    if re.match(r'(?:\d+\. |[-*+] )', unquote(body[start:])):
        while gap := re.match(r'\n\n+', body[end:stop]):
            following = end + gap.end()
            boundary = re.search(r'\n\n|\n(?=##+ )', body[following:stop])
            text = body[following:following+boundary.start()] if boundary else body[following:stop]
            if not re.match(r'(?:\d+\. |[-*+] |[ \t]+\S)', unquote(text)):
                break
            end = following + (boundary.start() if boundary else len(text))
    return end, level


def inject(cfg, model, rel, sections, body):
    if rel not in {'reader-work.md', 'reader-decision.md'} or not cfg.site.reader_paths:
        return body, []
    data = load_yaml(cfg.root / cfg.site.reader_paths)
    declared = placements(cfg, data, sections)
    role = PurePosixPath(rel).stem.removeprefix('reader-')
    selected = [item for item in declared if item['role'] == role]
    if not selected:
        return body, []
    if model is None:
        raise ValueError('Reader visuals require current facts')
    from .visuals import render_values
    definitions = load_yaml(definition_file(cfg))
    by_id = {value['id']: value for value in sections.values()}
    rendered, insertions, cache = [], [], {}
    for item in selected:
        source = by_id[item['section']]
        if source['id'] not in cache:
            # Render for the actual output path: normal download names and
            # source pins apply, while canonical prose stays byte-identical.
            cache[source['id']] = render_values(cfg, model, {**source, 'output': rel},
                                                  definitions['sections'].get(source['id'], []))
        found = [value for value in cache[source['id']] if value[0]['id'] == item['visual']]
        if len(found) != 1 or not found[0][2]:
            raise ValueError('Required reader visual missing or stale; it cannot be omitted')
        visual, block, code = found[0]
        position, level = _position(body, item['anchor'])
        block = re.sub(r'(?m)^#{3,4} ', '#'*(level+1)+' ', block, count=1)
        target = posixpath.relpath(section_output(source), posixpath.dirname(rel) or '.')
        block = re.sub(r'\]\(#(source-[0-9a-f]{16})\)',
                       lambda match: ']('+target+'#'+match[1]+')', block)
        insertions.append((position, block))
        rendered.append((visual, block, code))
    for position, block in sorted(insertions, reverse=True):
        body = body[:position]+'\n\n'+block+body[position:]
    return body, rendered
