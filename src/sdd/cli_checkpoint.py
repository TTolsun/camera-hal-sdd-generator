"""Atomic, receipt-bound checkpoints for completed CLI design units.

Only fully validated answers enter this store. Loading verifies original CLI
archives and reruns current deterministic checks and exact grounding verdicts.
It never turns an imported response into a new call or a human approval.
"""
from __future__ import annotations

import hashlib
import ast
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
    policy = {name: hashlib.sha256((root / (name + '.py')).read_bytes()).hexdigest()
              for name in ('manuscript', 'semantic', 'duplicates', 'design_contracts', 'validate')}
    selected = {'materialize', 'validate_answers', 'decode_unit', 'normalize_answer', '_validate_unit_response'}
    tree = ast.parse((root/'generated_design.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in selected]
    if {node.name for node in nodes} != selected:
        raise ValueError('Design validation policy functions are missing')
    policy['design_validation'] = hashlib.sha256(ast.dump(ast.Module(body=nodes, type_ignores=[]),
                                                         include_attributes=False).encode()).hexdigest()
    return policy


def style_policy(cfg):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(cfg.style_dir.glob('*.md'))}


def same_request_context(expected, actual):
    if actual.startswith(expected):
        return True  # Standard retries append the error after the full request.
    prefix, marker, suffix = expected.rpartition('\n출력:')
    return bool(marker and actual.startswith(prefix + '\n작성 조건: ')
                and actual.endswith(marker + suffix))  # Focused retries insert diagnostics before output.


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
    _indexes = {}

    def __init__(self, cfg, identity):
        self.cfg, self.identity = cfg, identity
        self.path = cfg.build_dir / 'cli-checkpoints' / (checksum(self.draft_identity(identity)) + '.json')
        self.canonical_path = self.path
        self.calls = cfg.build_dir / 'prompts' / 'calls'
        if not self.path.exists() and self.path.parent.exists():
            directory = reject_symlinks(self.path.parent).resolve()
            if directory not in self._indexes:
                index = {}
                for candidate in directory.glob('*.json'):
                    reject_symlinks(candidate)
                    try:
                        data = json.loads(candidate.read_text(encoding='utf-8'))
                        payload = data['payload']
                        if data['sha256'] != checksum(payload):
                            raise ValueError('checkpoint checksum mismatch')
                        key = checksum(self.compatible_identity(payload['identity']))
                        index.setdefault(key, candidate)
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        raise ValueError(f'CLI checkpoint is damaged: {candidate}: {exc}') from exc
                self._indexes[directory] = index
            compatible = self._indexes[directory].get(checksum(self.compatible_identity(identity)))
            if compatible is not None:
                self.path = compatible

    @staticmethod
    def draft_identity(identity):
        return {key: value for key, value in identity.items()
                if key not in ('validation_policy', 'grounding_policy')}

    @classmethod
    def compatible_identity(cls, identity):
        result = cls.draft_identity(identity)
        if isinstance(result.get('topic'), dict):
            result['topic'] = {key: value for key, value in result['topic'].items() if key != 'title'}
            if isinstance(result['topic'].get('answer_contract'), dict):
                result['topic']['answer_contract'] = {key: value for key, value in result['topic']['answer_contract'].items()
                                                       if key != 'reject_patterns'}
        # Actual system/user/schema, source revision and execution identity must
        # STILL match. Only a layout title and checks absent from the model's
        # input can use this path, always under current deterministic validation.
        return result

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
                    or self.compatible_identity(payload['identity']) != self.compatible_identity(self.identity)
                    or not isinstance(payload['receipts'], list) or not payload['receipts']):
                raise ValueError('checkpoint identity or checksum mismatch')
            records = self._records(payload['receipts'])
            request = self.identity['request']
            if not any(row.raw == payload['raw'] and row.request['system'] == request['system']
                       and same_request_context(request['user'], row.request['user'])
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
            save(self.canonical_path, dict(schema=1, payload=payload, sha256=checksum(payload)), newline='\n')
            self.path = self.canonical_path
            self._indexes.setdefault(self.path.parent.resolve(), {})[
                checksum(self.compatible_identity(self.identity))] = self.path
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
