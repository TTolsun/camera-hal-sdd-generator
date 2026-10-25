"""Revalidate actual archived HTTP answers during an explicitly repaired trial.

This never invents a response or approves a manuscript. Exact source/question
context is retained; changed lexical checks are reapplied by generated_design.
Grounding verdicts are reused only for the exact current review request.
"""
import hashlib
import json
import re
from pathlib import Path


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def context(request):
    user = request['user']
    start = user.index('{')
    payload, _ = json.JSONDecoder().raw_decode(user[start:])
    if 'sources' not in payload or 'topic' not in payload:
        raise ValueError('Not a generation request')
    # Terms and known-error patterns are validation policy, not evidence.
    # Reapply them to the unchanged model text rather than discarding it.
    if 'answer_contract' in payload:
        payload['answer_contract'] = {'basis': payload['answer_contract']['basis']}
    return sha({'system': request['system'], 'instruction': user[:start],
                'payload': payload, 'response_schema': request.get('response_schema')})


class Archive:
    def __init__(self, root: Path, cfg):
        self.records = []
        self.exact = {}
        settings = {key: getattr(cfg, key) for key in ('temperature', 'think', 'num_ctx', 'max_output_tokens')}
        for path in sorted(root.rglob('*.receipt.json')):
            receipt = json.loads(path.read_text(encoding='utf-8'))
            prefix = path.name.removesuffix('.receipt.json')
            request = json.loads(path.with_name(prefix + '.request.json').read_text(encoding='utf-8'))
            raw = path.with_name(prefix + '.response.txt').read_bytes().decode('utf-8')
            if receipt['request_sha256'] != sha(request) or receipt['response_sha256'] != hashlib.sha256(raw.encode()).hexdigest():
                raise ValueError('HTTP replay archive checksum mismatch: ' + path.name)
            if (receipt.get('http_call') is not True or receipt.get('transport') != cfg.kind
                    or receipt.get('model') != cfg.model or receipt.get('settings') != settings
                    or receipt.get('provider', {}).get('done_reason') == 'length'
                    or receipt.get('provider', {}).get('finish_reason') == 'length'):
                continue
            record = {'raw': raw, 'request': request, 'receipt': path.relative_to(root).as_posix(),
                      'request_sha256': receipt['request_sha256'], 'response_sha256': receipt['response_sha256'],
                      'tag': receipt['tag'], 'completed_at': receipt.get('completed_at', '')}
            self.exact.setdefault(receipt['request_sha256'], []).append(record)
            try:
                record['context'] = context(request)
                self.records.append(record)
            except (ValueError, TypeError, KeyError):
                pass  # Review and non-generation requests are not producer answers.
        self.records.sort(key=lambda row: row['completed_at'], reverse=True)

    def candidates(self, system, user, schema, tag):
        key = context({'system': system, 'user': user, 'response_schema': schema})
        seen = set()
        for record in self.records:
            if (record['context'] == key and re.fullmatch(re.escape(tag) + r'_\d+(?:_revision)?', record['tag'])
                    and record['response_sha256'] not in seen):
                seen.add(record['response_sha256'])
                yield record

    def reviewer(self, agent):
        archive = self
        class Reviewer:
            def chat(self, system, user, **kwargs):
                key = sha({'system': system, 'user': user, 'response_schema': kwargs.get('response_schema')})
                rows = archive.exact.get(key, [])
                if rows:
                    return max(rows, key=lambda row: row['completed_at'])['raw']
                return agent.chat(system, user, **kwargs)
        return Reviewer()
