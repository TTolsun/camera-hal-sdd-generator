"""Bind generated explanations to archived real model calls, without rewriting text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .export_html import _split
from .generated_design import normalize_answer, resolve_passages


def verify_calls(model, manuscripts: Path, calls: Path, *, provider: str, model_name: str,
                 allow_reused: bool = False) -> dict:
    responses = []
    json_responses = []
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
        if (receipt.get('provider', {}).get('done_reason') == 'length'
                or receipt.get('provider', {}).get('finish_reason') == 'length'):
            continue  # An archived partial response cannot establish authorship.
        try:
            data = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
            json_responses.append((receipt['tag'], data))
            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
            sources = payload['sources']
            passages = {item['quote_id']: (sid, item['text'].strip())
                        for sid, blocks in sources.items() for item in blocks if item.get('quote_id')}
            statements = resolve_passages(data['statements'], passages)
            normalize_answer(model, statements, ['\n'.join(b['text'] for b in blocks) for blocks in sources.values()] + [payload.get('topic', '')])
        except (ValueError, KeyError, TypeError, AttributeError):
            continue  # Invalid retry responses cannot establish manuscript provenance.
        responses.append((receipt['tag'], statements))
    documents, topics, statements, visuals = 0, 0, 0, 0
    for path in manuscripts.rglob('*.md'):
        metadata, _ = _split(path.read_text(encoding='utf-8'))
        sid = metadata.get('section')
        for vid, record in metadata.get('generated_visuals', {}).get('records', {}).items():
            if not sid or record.get('producer') != f'{provider}/{model_name}':
                raise ValueError(f'Visual model identity mismatch: {path.name}/{vid}')
            if record.get('reused') and not allow_reused:
                raise ValueError('A full fresh-model trial cannot reuse previous visual drafts.')
            prefix = f'visual_{sid}_{vid}_'
            if not any(re.fullmatch(re.escape(prefix) + r'\d+', tag) and data == record.get('draft')
                       for tag, data in json_responses):
                raise ValueError(f'No matching HTTP visual response for {sid}/{vid}')
            visuals += 1
        artifact = metadata.get('generated_design')
        if not artifact:
            continue
        if (artifact.get('reused_topics') or artifact.get('replayed_units')) and not allow_reused:
            raise ValueError('A full fresh-model trial cannot reuse previous topic answers.')
        if not sid:
            raise ValueError(f'Missing manuscript section identity: {path.name}')
        documents += 1
        for tid, answers in artifact['answers'].items():
            topics += 1
            for answer in answers:
                part = answer.get('part_id')
                tag_prefix = f'{sid}_{tid}_' + (part + '_' if part else '')
                possible = [item for tag, result in responses
                            if re.fullmatch(re.escape(tag_prefix) + r'\d+(?:_revision)?', tag) for item in result]
                original = {key: value for key, value in answer.items() if key != 'part_id'}
                if original not in possible:
                    raise ValueError(f'No matching HTTP model response for {sid}/{tid}')
                statements += 1
    return {'documents': documents, 'topics': topics, 'statements': statements, 'visuals': visuals,
            'previous_http_answers_allowed': allow_reused,
            'verified_http_calls': len(list(calls.rglob('*.receipt.json'))),
            'scope': 'Exact request/response hashes and model authorship; not semantic or human approval.'}


def main():
    import argparse
    from .facts.model import KnowledgeModel
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--manuscripts', type=Path, required=True)
    parser.add_argument('--calls', type=Path, required=True)
    parser.add_argument('--provider', choices=('ollama', 'openai-compatible'), required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--allow-reused', action='store_true', help='Also verify retained answers against archived HTTP calls')
    args = parser.parse_args()
    report = verify_calls(KnowledgeModel.load(args.facts), args.manuscripts, args.calls,
                          provider=args.provider, model_name=args.model, allow_reused=args.allow_reused)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
