"""Local product facts and non-source evidence, scoped to existing design topics.

Hashes authenticate selected bytes, never their truth or a person's approval.
No network requests, model calls or second publication ledger live here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import Decimal
from datetime import date
from pathlib import PurePosixPath

import yaml
from jsonschema import Draft202012Validator

from .reader_scope import TEXT, obj

ID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_-]{0,63}$'}
STRINGS = {'type': 'array', 'uniqueItems': True, 'items': TEXT}
STATES = ['unknown', 'offered', 'unsupported']
CLAIMS = ['structural', 'performance', 'comparison', 'support']
DOCUMENT = obj({
    'id': ID, 'type': {'enum': ['specification', 'release', 'measurement', 'comparison', 'project-document']},
    'supplier': TEXT, 'version': TEXT, 'date': TEXT, 'valid_until': TEXT,
    'product': ID, 'release': TEXT, 'configuration': TEXT, 'feature': ID,
    'conditions': STRINGS, 'availability': {'enum': STATES}, 'file': TEXT,
    'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
})
FEATURE = obj({
    'id': ID, 'need': TEXT, 'usage': TEXT, 'availability': {'enum': STATES},
    'conditions': STRINGS, 'exclusions': STRINGS, 'implementation': STRINGS,
    'evidence': STRINGS, 'claims': {'type': 'array', 'items': obj({
        'kind': {'enum': CLAIMS}, 'evidence': STRINGS})},
})
PRODUCT = obj({'id': ID, 'scope': {'enum': ['project', 'product']}, 'release': TEXT, 'configuration': TEXT,
               'simulation': {'type': 'boolean'}, 'as_of': TEXT,
               'features': {'type': 'array', 'minItems': 1, 'items': FEATURE}})
SCHEMA = obj({'schema': {'const': 1}, 'products': {'type': 'array', 'items': PRODUCT},
              'evidence': {'type': 'array', 'items': DOCUMENT}})


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _unique(values, label):
    ids = [v['id'] for v in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f'Duplicate product {label} IDs.')
    return {v['id']: v for v in values}


def _local(root, rel):
    path = PurePosixPath(rel)
    target = (root / rel).resolve()
    if (path.is_absolute() or '..' in path.parts or ':' in rel or '\\' in rel
            or not target.is_relative_to(root.resolve())):
        raise ValueError('Product evidence must be a local relative file inside the product input directory.')
    return target


def input_paths(cfg):
    """Keep local product assets inside existing snapshot/trial boundaries."""
    options = cfg.raw.get('products', {})
    if not isinstance(options, dict) or not options.get('file'):
        return []
    path = cfg.paths.get('products_file') or _local(cfg.root, options['file'])
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(SCHEMA).iter_errors(data))
    if errors:
        raise ValueError('Product input: ' + errors[0].message)
    return [path, *[_local(path.parent, d['file']) for d in data['evidence']]]


def bind(cfg, sections):
    """Attach only selected facts/materials; unrelated products cannot invalidate prose."""
    for section in sections:
        for topic in section.get('design_topics', []):
            if '_product_context' in topic or any(s.get('kind') == 'product' for s in topic.get('sources', [])):
                raise ValueError('Product context and material source selectors are generator-owned; use topic.product.')
    bindings = [t for s in sections for t in s.get('design_topics', []) if 'product' in t]
    if not bindings:
        return sections
    options = cfg.raw.get('products', {})
    if not isinstance(options, dict) or set(options) != {'file'} or not isinstance(options['file'], str):
        raise ValueError('Product topics require products.file (local YAML).')
    path = cfg.paths.get('products_file') or _local(cfg.root, options['file'])
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(SCHEMA).iter_errors(data))
    if errors:
        raise ValueError('Product input: ' + errors[0].message)
    products = _unique(data['products'], 'product')
    documents = _unique(data['evidence'], 'evidence')
    result = copy.deepcopy(sections)
    for section in result:
        for topic in section.get('design_topics', []):
            if 'product' not in topic:
                continue
            binding = topic['product']
            if (not isinstance(binding, dict) or set(binding) != {'id', 'feature'}
                    or not all(isinstance(v, str) for v in binding.values())):
                raise ValueError('Topic product requires id and feature.')
            product = products.get(binding['id'])
            if product is None:
                raise ValueError('Unknown selected product.')
            features = _unique(product['features'], 'feature')
            feature = features.get(binding['feature'])
            if feature is None:
                raise ValueError('Unknown selected product feature.')
            sources = topic.get('sources', [])
            if not set(feature['implementation']) <= {s['id'] for s in sources}:
                raise ValueError('Product implementation must reference this topic\'s existing pinned source IDs.')
            selected_ids = set(feature['evidence']) | {eid for claim in feature['claims'] for eid in claim['evidence']}
            selected, materials = {}, {}
            as_of = date.fromisoformat(product['as_of'])
            for eid in sorted(selected_ids):
                doc = documents.get(eid)
                if doc is None:
                    raise ValueError(f'Unknown product evidence {eid}.')
                if any(doc[k] != product[k] for k in ('release', 'configuration')) or doc['product'] != product['id'] or doc['feature'] != feature['id']:
                    raise ValueError(f'{eid}: wrong product/release/configuration/feature evidence.')
                if not date.fromisoformat(doc['date']) <= as_of <= date.fromisoformat(doc['valid_until']):
                    raise ValueError(f'{eid}: stale or future product evidence.')
                if set(doc['conditions']) != set(feature['conditions']):
                    raise ValueError(f'{eid}: evidence conditions differ from selected product conditions.')
                raw = _local(path.parent, doc['file']).read_bytes()
                if digest(raw) != doc['sha256']:
                    raise ValueError(f'{eid}: product evidence bytes changed.')
                text = raw.decode('utf-8')
                if not text.strip():
                    raise ValueError(f'{eid}: empty product evidence.')
                selected[eid] = doc
                materials[eid] = text
            states = {d['availability'] for d in selected.values() if d['availability'] != 'unknown'}
            if len(states) > 1 or (states and feature['availability'] != 'unknown' and feature['availability'] not in states):
                raise ValueError('Conflicting product availability evidence.')
            assurance_types = {'specification', 'release'} | ({'project-document'} if product['scope'] == 'project' else set())
            assurance = [d for d in selected.values() if d['type'] in assurance_types
                         and d['availability'] == feature['availability'] != 'unknown']
            availability = feature['availability'] if assurance else 'unknown'
            allowed, unresolved = [], []
            for claim in feature['claims']:
                kind = claim['kind']
                kinds = {selected[eid]['type'] for eid in claim['evidence']}
                supported = ((kind == 'structural' and bool(feature['implementation']))
                             or (kind == 'performance' and 'measurement' in kinds)
                             or (kind == 'comparison' and 'comparison' in kinds)
                             or (kind == 'support' and availability != 'unknown' and any(
                                 selected[eid] in assurance for eid in claim['evidence'])))
                (allowed if supported else unresolved).append(kind)
            context = {'product': {k: v for k, v in product.items() if k != 'features'},
                       'feature': feature, 'availability': availability,
                       'implementation': 'source-bound' if feature['implementation'] else 'unknown',
                       'measurement': 'conditional' if any(d['type'] == 'measurement' for d in selected.values()) else 'unknown',
                       'allowed_claims': sorted(set(allowed)), 'unresolved_claims': sorted(set(unresolved)),
                       'evidence': selected, 'human_review': 'pending'}
            topic['_product_context'] = context
            for eid, text in materials.items():
                source_id = 'product-' + eid
                if any(s['id'] == source_id for s in sources):
                    raise ValueError('Product/source ID collision.')
                # Synthetic citation namespace is never linked to the source Git host.
                doc = selected[eid]
                sources.append({'id': source_id, 'file': f"product-evidence/{product['id']}/{eid}.txt",
                                'start': source_id, 'end': source_id, 'kind': 'product',
                                'product_record': doc, 'text': text})
                for part in topic.get('parts', []):
                    part['sources'].append(source_id)
            topic['sources'] = sources
    return result


def record(source, commit):
    text = source['text']
    return {'commit': commit, 'selector': source, 'status': 'available', 'origin': 'product-material',
            'product_record': source['product_record'], 'file': source['file'], 'line': 1,
            'end_line': text.count('\n') + 1, 'text': text, 'sha256': digest(text.encode()), 'whole_file': True}


_PERFORMANCE_NUMBER = re.compile(r'(\d+(?:\.\d+)?)\s*(fps|ms|초|%|배\b)', re.I)


def _recorded_timeout(topic, text, match):
    """A recorded test timeout is a parameter, not capture performance.

    Exempt only time units immediately labelled as a timeout/limit, whose value
    is explicitly present in a selected JSON measurement's timeout fields.
    Unlabelled latency, fps and unsupported numbers retain the normal guard.
    """
    if match[2].lower() not in ('ms', '초'):
        return False
    before = text[:match.start()].replace('`', '')
    after = text[match.end():].replace('`', '')
    label = r'(?:시간\s*(?:제한|초과)|타임아웃|timeout)'
    if not (re.search(label + r'(?:\s*(?:프로브|probe))?[\s(:은는이가]*$', before, re.I)
            or re.match(r'[\s)\]:의]*' + label, after, re.I)):
        return False
    values = set()

    def collect(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if (key in ('timeout_seconds', 'timeout_sec')
                        or (key == 'seconds' and type(item.get('timed_out')) is bool)):
                    if type(value) in (int, float) and value > 0:
                        values.add(Decimal(str(value)))
                collect(value)
        elif isinstance(item, list):
            for value in item:
                collect(value)
    for source in topic.get('sources', []):
        if source.get('kind') == 'product' and source.get('product_record', {}).get('type') == 'measurement':
            try:
                collect(json.loads(source.get('text', '')))
            except (ValueError, TypeError):
                continue
    seconds = Decimal(match[1]) / (1000 if match[2].lower() == 'ms' else 1)
    return seconds in values


def validate_text(topic, statements):
    context = topic.get('_product_context')
    if context is None:
        return
    allowed = set(context['allowed_claims'])
    for statement in statements:
        text = statement['text']
        if 'performance' not in allowed and any(not _recorded_timeout(topic, text, match)
                                               for match in _PERFORMANCE_NUMBER.finditer(text)):
            raise ValueError('Product performance number lacks selected measurement evidence.')
        if 'comparison' not in allowed and re.search(r'경쟁.*(?:우위|우수)|더 빠|가장 빠|최고 성능|faster than|best performance', text, re.I):
            raise ValueError('Product comparison lacks selected comparison evidence.')
        if context['availability'] != 'offered' and re.search(r'(?<!미)지원합니다|제공합니다|보장합니다', text):
            raise ValueError('Implementation/unknown/unsupported cannot become a product offering guarantee.')


def scope_notice(topic):
    context = topic.get('_product_context')
    if not context or not context['product']['simulation']:
        return ''
    # A model omission cannot turn a fictional fixture into a real product
    # claim. This is deterministic provenance text, never generated marketing.
    return '**가상 시험 구성입니다. 실제 제품의 지원·성능 주장으로 사용하지 마세요.**\n\n'
