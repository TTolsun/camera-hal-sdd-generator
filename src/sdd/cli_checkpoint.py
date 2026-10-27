"""Atomic, receipt-bound checkpoints for completed CLI design units.

Only fully validated answers enter this store. Loading verifies original CLI
archives and reruns current deterministic checks and exact grounding verdicts.
It never turns an imported response into a new call or a human approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .call_records import canonical_request_hash, load_record
from .cli_provenance import verify_cli_receipt
from .state_io import save
from .trial_workspace import contained_path, reject_symlinks
from .llm import AgentError


def checksum(value):
    return canonical_request_hash(value)


def validation_policy():
    # Lexical/source/contract checks are distinct from model entailment policy.
    # Content hashes change with code; no compatibility aliases are added here.
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / (name + '.py')).read_bytes()).hexdigest()
            for name in ('manuscript', 'semantic', 'duplicates', 'design_contracts', 'validate')}


def style_policy(cfg):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(cfg.style_dir.glob('*.md'))}


class Capture:
    def __init__(self, agent):
        self.agent, self.receipts = agent, []

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def chat(self, system, user, **kwargs):
        raw = self.agent.chat(system, user, **kwargs)
        path = getattr(self.agent, 'last_receipt', None)
        if path is not None:
            self.receipts.append(Path(path))
        return raw


class UnitStore:
    def __init__(self, cfg, identity):
        self.cfg, self.identity = cfg, identity
        self.path = cfg.build_dir / 'cli-checkpoints' / (checksum(self.draft_identity(identity)) + '.json')
        self.calls = cfg.build_dir / 'prompts' / 'calls'

    @staticmethod
    def draft_identity(identity):
        return {key: value for key, value in identity.items()
                if key not in ('validation_policy', 'grounding_policy')}

    def _records(self, paths):
        rows = []
        for name in paths:
            path = contained_path(self.calls, name)
            record = load_record(path, root=self.calls)
            verify_cli_receipt(record.request, record.raw, record.receipt, self.calls, self.cfg.agent)
            arguments = record.receipt['provider'].get('arguments')
            # A historical receipt without actual CLI arguments is insufficient
            # for this optimization; ordinary manuscript provenance is separate.
            from .cli_agent import command, arguments as invocation_arguments
            expected = command(self.cfg.agent)[1:] + invocation_arguments(self.cfg.agent, record.request['response_schema'])
            if arguments != expected:
                raise ValueError('CLI checkpoint arguments mismatch')
            rows.append(record)
        return rows

    def read(self):
        if not self.path.exists():
            return None
        try:
            reject_symlinks(self.path)
            data = json.loads(self.path.read_text(encoding='utf-8'))
            payload = data['payload']
            if (data['sha256'] != checksum(payload)
                    or self.draft_identity(payload['identity']) != self.draft_identity(self.identity)
                    or not isinstance(payload['receipts'], list) or not payload['receipts']):
                raise ValueError('checkpoint identity or checksum mismatch')
            records = self._records(payload['receipts'])
            request = self.identity['request']
            if not any(row.raw == payload['raw'] and row.request['system'] == request['system']
                       and row.request['user'].startswith(request['user'])
                       and row.request.get('response_schema') == request['response_schema'] for row in records):
                raise ValueError('validated response has no completed CLI receipt')
            return payload, Reviewer(records)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ValueError(f'CLI checkpoint is damaged; previous output preserved: {self.path}: {exc}') from exc

    def write(self, raw, statements, capture):
        if not capture.receipts:
            # A custom ChatPort without an archive is allowed, but cannot certify
            # a durable checkpoint as a real CLI call.
            return
        try:
            paths = [path.resolve().relative_to(self.calls.resolve()).as_posix() for path in capture.receipts]
            self._records(paths)
            payload = dict(identity=self.identity, raw=raw, statements=statements, receipts=paths)
            save(self.path, dict(schema=1, payload=payload, sha256=checksum(payload)), newline='\n')
        except (ValueError, OSError) as exc:
            raise AgentError(f'CLI checkpoint persistence failed; previous output preserved: {exc}') from exc


class Reviewer:
    def __init__(self, records):
        self.records = {canonical_request_hash(row.request): row.raw for row in records}

    def chat(self, system, user, **kwargs):
        key = canonical_request_hash(dict(system=system, user=user, response_schema=kwargs.get('response_schema')))
        if key not in self.records:
            raise ValueError('CLI checkpoint lacks the exact current grounding review receipt')
        return self.records[key]
