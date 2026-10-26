"""Revalidate actual archived HTTP answers during an explicitly repaired trial.

This never invents a response or approves a manuscript. Exact source/question
context is retained; changed lexical checks are reapplied by generated_design.
Grounding verdicts are reused only for the exact current review request.
"""
import hashlib
import json
import re
from pathlib import Path

from .call_records import canonical_request_hash, iter_records
from .trial_workspace import reject_symlinks


def sha(value):
    return canonical_request_hash(value)


def context(request):
    user = request['user']
    start = user.index('{')
    payload, _ = json.JSONDecoder().raw_decode(user[start:])
    if user.startswith('근거:\n'):
        # Focused prompts put sources first and questions after that JSON.
        # Retain the entire message, including its question/output suffix;
        # changing any of it requires a new real call.
        return sha(request)
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
        root = reject_symlinks(root).resolve()
        settings = {key: getattr(cfg, key) for key in ('temperature', 'think', 'num_ctx', 'max_output_tokens')}
        for loaded in iter_records(root):
            receipt, request, raw = loaded.receipt, loaded.request, loaded.raw
            if (receipt.get('http_call') is not True or receipt.get('cli_call') is True
                    or receipt.get('transport') != cfg.kind
                    or receipt.get('model') != cfg.model or receipt.get('settings') != settings
                    or receipt.get('provider', {}).get('done_reason') == 'length'
                    or receipt.get('provider', {}).get('finish_reason') == 'length'):
                continue
            record = {'raw': raw, 'request': request, 'receipt': loaded.receipt_path.relative_to(root).as_posix(),
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
        try:
            key = context({'system': system, 'user': user, 'response_schema': schema})
        except (ValueError, TypeError, KeyError):
            return  # An unsupported prompt format must make a new real call.
        seen = set()
        for record in self.records:
            if (record['context'] == key and re.fullmatch(re.escape(tag) + r'_\d+(?:_revision)?', record['tag'])
                    and record['response_sha256'] not in seen):
                seen.add(record['response_sha256'])
                yield record

    def reviewer(self, agent):
        archive = self
        class Reviewer:
            def __init__(self):
                self.replayed_http_calls = 0
                self.translation_replays = []
            def translation_candidates(self, system):
                rows = sorted((r for items in archive.exact.values() for r in items),
                              key=lambda r: r['completed_at'])
                for record in rows:
                    if record['request']['system'] != system:
                        continue
                    try:
                        request, _ = json.JSONDecoder().raw_decode(record['request']['user'])
                        sources = request['texts']
                        response = json.loads(record['raw'])
                        if not isinstance(response, dict) or set(response) != {'translations'}:
                            continue
                        values = response['translations']
                        fields = record['request']['response_schema']['properties']['translations']['properties']
                        if (not isinstance(sources, dict) or not isinstance(values, dict)
                                or sources.keys() != values.keys() or fields.keys() != sources.keys()
                                or any(not isinstance(s, str) for s in sources.values())
                                or any(fields[k].get('type') != 'string' for k in sources)):
                            continue
                        yield record, sources, values
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
            def record_translation_reuse(self, record, sources):
                self.replayed_http_calls += 1
                self.translation_replays.append({key: record[key] for key in
                    ('receipt', 'request_sha256', 'response_sha256')} |
                    {'source_sha256': [hashlib.sha256(s.encode()).hexdigest() for s in sources]})
            def fresh_chat(self, system, user, **kwargs):
                return agent.chat(system, user, **kwargs)
            def chat(self, system, user, **kwargs):
                key = sha({'system': system, 'user': user, 'response_schema': kwargs.get('response_schema')})
                rows = archive.exact.get(key, [])
                if rows:
                    self.replayed_http_calls += 1
                    return max(rows, key=lambda row: row['completed_at'])['raw']
                return agent.chat(system, user, **kwargs)
        return Reviewer()
