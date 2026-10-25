"""Bind generated explanations to archived real model calls, without rewriting text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .export_html import _split
from .generated_design import normalize_answer, resolve_passages


def verify_calls(model, manuscripts: Path, calls: Path, *, provider: str, model_name: str) -> dict:
    responses = []
    for receipt_path in sorted(calls.rglob('*.receipt.json')):
        prefix = receipt_path.name.removesuffix('.receipt.json')
        request_path = receipt_path.with_name(prefix + '.request.json')
        response_path = receipt_path.with_name(prefix + '.response.txt')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        request = json.loads(request_path.read_text(encoding='utf-8'))
        raw = response_path.read_bytes().decode('utf-8')
        request_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if (receipt.get('request_sha256') != request_hash
                or receipt.get('response_sha256') != hashlib.sha256(raw.encode()).hexdigest()
                or receipt.get('http_call') is not True or receipt.get('transport') != provider
                or receipt.get('model') != model_name):
            raise ValueError(f'Model call receipt mismatch: {receipt_path.name}')
        user = request['user']
        try:
            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
            sources = payload['sources']
            passages = {item['quote_id']: (sid, item['text'].strip())
                        for sid, blocks in sources.items() for item in blocks if item.get('quote_id')}
            data = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
            statements = resolve_passages(data['statements'], passages)
            normalize_answer(model, statements, ['\n'.join(b['text'] for b in blocks) for blocks in sources.values()])
        except (ValueError, KeyError, TypeError):
            continue  # Invalid retry responses cannot establish manuscript provenance.
        responses.append((receipt['tag'], statements))
    documents, topics, statements = 0, 0, 0
    for path in manuscripts.rglob('*.md'):
        metadata, _ = _split(path.read_text(encoding='utf-8'))
        artifact = metadata.get('generated_design')
        if not artifact:
            continue
        if artifact.get('reused_topics'):
            raise ValueError('A full fresh-model trial cannot reuse previous topic answers.')
        sid = metadata.get('section')
        if not sid:
            raise ValueError(f'Missing manuscript section identity: {path.name}')
        documents += 1
        for tid, answers in artifact['answers'].items():
            topics += 1
            possible = [answer for tag, result in responses if tag.startswith(f'{sid}_{tid}_') for answer in result]
            for answer in answers:
                if answer not in possible:
                    raise ValueError(f'No matching HTTP model response for {sid}/{tid}')
                statements += 1
    return {'documents': documents, 'topics': topics, 'statements': statements,
            'verified_http_calls': len(list(calls.rglob('*.receipt.json'))),
            'scope': 'Exact request/response hashes and model authorship; not semantic or human approval.'}
