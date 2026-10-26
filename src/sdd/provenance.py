"""Bind generated explanations to archived real model calls, without rewriting text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .document_metadata import split_frontmatter as _split
from .generated_design import normalize_answer, resolve_passages
from .config import AgentConfig
from .cli_agent import RUNNERS
from .cli_provenance import verify_cli_receipt
from .llm import LIVE_KINDS


def same_answer(left, right):
    # Generator versions can add code typography using newly available scope
    # names. Only backticks may differ; every source word and other field stays
    # exact. The manuscript validator still checks its code/HTML formatting.
    def identity(answer):
        return {**answer, 'text': answer['text'].replace('`', '')}
    return identity(left) == identity(right)


def verify_calls(model, manuscripts: Path, calls: Path, *, provider: str, model_name: str,
                 allow_reused: bool = False, runner: str | None = None) -> dict:
    if provider not in LIVE_KINDS:
        raise ValueError('Provenance requires real CLI or HTTP call archives')
    if provider == 'cli' and (runner not in RUNNERS or allow_reused):
        raise ValueError('CLI provenance requires a selected runner and fresh calls; reuse is unsupported')
    expected = AgentConfig(kind=provider, model=model_name, runner=runner or 'hermes')
    transport_label = 'CLI' if provider == 'cli' else 'HTTP'
    responses = []
    json_responses = []
    verified_http, verified_cli = 0, 0
    for receipt_path in sorted(calls.rglob('*.receipt.json')):
        prefix = receipt_path.name.removesuffix('.receipt.json')
        request_path = receipt_path.with_name(prefix + '.request.json')
        response_path = receipt_path.with_name(prefix + '.response.txt')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        request = json.loads(request_path.read_text(encoding='utf-8'))
        raw = response_path.read_bytes().decode('utf-8')
        if provider == 'cli':
            verify_cli_receipt(request, raw, receipt, calls, expected)
            verified_cli += 1
        else:
            request_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if (receipt.get('request_sha256') != request_hash
                    or receipt.get('response_sha256') != hashlib.sha256(raw.encode()).hexdigest()
                    or receipt.get('http_call') is not True or receipt.get('cli_call') is True
                    or receipt.get('transport') != provider
                    or receipt.get('model') != model_name):
                raise ValueError(f'Model call receipt mismatch: {receipt_path.name}')
            verified_http += 1
        user = request['user']
        if (receipt.get('provider', {}).get('done_reason') == 'length'
                or receipt.get('provider', {}).get('finish_reason') == 'length'):
            continue  # An archived partial response cannot establish authorship.
        try:
            data = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
            json_responses.append((receipt['tag'], data))
            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
            if 'sources' in payload:
                sources = payload['sources']
            elif user.startswith('근거:\n'):
                sources = payload
                payload = {'topic': user.split('\n질문: ', 1)[1].split('\n출력: ', 1)[0]}
            else:
                continue
            passages = {item['quote_id']: (sid, item['text'].strip())
                        for sid, blocks in sources.items() for item in blocks if item.get('quote_id')}
            statements = resolve_passages(data['statements'], passages)
            normalize_answer(model, statements, ['\n'.join(b['text'] for b in blocks) for blocks in sources.values()] + [payload.get('topic', ''), *[value for blocks in sources.values() for block in blocks
                for value in block.get('scope', {}).values()]])
        except (ValueError, KeyError, TypeError, AttributeError):
            continue  # Invalid retry responses cannot establish manuscript provenance.
        responses.append((receipt['tag'], statements))
    documents, topics, statements, visuals = 0, 0, 0, 0
    for path in manuscripts.rglob('*.md'):
        metadata, _ = _split(path.read_text(encoding='utf-8'))
        sid = metadata.get('section')
        for vid, record in metadata.get('generated_visuals', {}).get('records', {}).items():
            if not sid or record.get('producer') != expected.label:
                raise ValueError(f'Visual model identity mismatch: {path.name}/{vid}')
            if record.get('reused') and not allow_reused:
                raise ValueError('A full fresh-model trial cannot reuse previous visual drafts.')
            prefix = f'visual_{sid}_{vid}_'
            if not any(re.fullmatch(re.escape(prefix) + r'\d+', tag) and data == record.get('draft')
                       for tag, data in json_responses):
                raise ValueError(f'No matching {transport_label} visual response for {sid}/{vid}')
            visuals += 1
        artifact = metadata.get('generated_design')
        if not artifact:
            continue
        if (artifact.get('reused_topics') or artifact.get('replayed_units')) and not allow_reused:
            raise ValueError('A full fresh-model trial cannot reuse previous topic answers.')
        if not sid:
            raise ValueError(f'Missing manuscript section identity: {path.name}')
        origins = artifact.get('topic_agents', {})
        if (provider == 'cli' and set(origins) != set(artifact['answers'])) or any(
                value != expected.label for value in origins.values()):
            raise ValueError(f'Topic model identity mismatch: {path.name}')
        documents += 1
        for tid, answers in artifact['answers'].items():
            topics += 1
            for answer in answers:
                part = answer.get('part_id')
                tag_prefix = f'{sid}_{tid}_' + (part + '_' if part else '')
                possible = [item for tag, result in responses
                            if re.fullmatch(re.escape(tag_prefix) + r'\d+(?:_revision)?', tag) for item in result]
                if 'subpart_id' in answer:
                    tag_prefix += f"sub{answer['subpart_id']}_"
                    possible = [item for tag, result in responses
                                if re.fullmatch(re.escape(tag_prefix) + r'\d+(?:_revision)?', tag) for item in result]
                original = {key: value for key, value in answer.items() if key not in ('part_id', 'subpart_id')}
                if not any(same_answer(original, item) for item in possible):
                    raise ValueError(f'No matching {transport_label} model response for {sid}/{tid}')
                statements += 1
    return {'documents': documents, 'topics': topics, 'statements': statements, 'visuals': visuals,
            'previous_http_answers_allowed': allow_reused,
            'verified_http_calls': verified_http, 'verified_cli_calls': verified_cli,
            'producer': expected.label,
            'scope': 'Exact request/response hashes and model authorship, allowing code backtick typography only; not semantic or human approval.'}


def main():
    import argparse
    from .facts.model import KnowledgeModel
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--manuscripts', type=Path, required=True)
    parser.add_argument('--calls', type=Path, required=True)
    parser.add_argument('--provider', choices=LIVE_KINDS, required=True)
    parser.add_argument('--model', default='', help='Configured model; omit only for the CLI default')
    parser.add_argument('--runner', choices=RUNNERS, help='Required with --provider cli')
    parser.add_argument('--allow-reused', action='store_true', help='Also verify retained answers against archived HTTP calls')
    args = parser.parse_args()
    if args.provider == 'cli' and not args.runner:
        parser.error('--provider cli requires --runner')
    if args.provider != 'cli' and not args.model:
        parser.error('HTTP provenance requires --model')
    report = verify_calls(KnowledgeModel.load(args.facts), args.manuscripts, args.calls,
                          provider=args.provider, model_name=args.model, runner=args.runner,
                          allow_reused=args.allow_reused)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
