"""Validate CLI call archives without executing a runner or changing manuscripts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .config import AgentConfig
from .cli_agent import RUNNERS, build_prompt as assemble_prompt, decode_response
from .trial_workspace import is_link

PromptBuilder = Callable[[str, str, dict | None], str]
StdoutDecoder = Callable[[str, str], tuple[str, dict]]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _stdout_file(calls: Path, name: Any) -> Path:
    # cli_agent stores POSIX paths relative to dump_dir, the parent of calls/.
    # Reject traversal before resolution and links even when their target is inside.
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('Unsafe CLI stdout path')
    parts = name.split('/')
    if len(parts) < 2 or parts[0] != 'cli' or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Unsafe CLI stdout path')
    if PurePosixPath(name).is_absolute():
        raise ValueError('Unsafe CLI stdout path')
    if is_link(calls):
        raise ValueError('Linked CLI calls directory is not allowed')
    try:
        if not calls.is_dir():
            raise ValueError('CLI calls archive is not a directory')
        base = calls.resolve(strict=True).parent
        path = base.joinpath(*parts)
        current = path
        while current != base:
            if is_link(current):
                raise ValueError('Linked CLI stdout path is not allowed')
            current = current.parent
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(base / 'cli') or not resolved.is_file():
            raise ValueError('Unsafe CLI stdout path')
        return resolved
    except OSError as exc:
        raise ValueError('CLI stdout archive is missing or unreadable') from exc


def verify_cli_receipt(request: dict, response: str, receipt: dict, calls: Path,
                       expected: AgentConfig, *, build_prompt: PromptBuilder = assemble_prompt,
                       decode_stdout: StdoutDecoder = decode_response) -> dict:
    """Bind a saved response to the selected CLI's prompt and completed raw output.

    Pass the same prompt builder and decoder used by cli_agent.chat. Callbacks
    keep transport formatting in that module rather than duplicating it here.
    This checks archive integrity, not semantic correctness or human approval.
    A CLI's default model remains an unverified runtime selection.
    """
    if expected.kind != 'cli' or expected.runner not in RUNNERS:
        raise ValueError('CLI provenance requires an explicitly selected CLI runner')
    if not isinstance(receipt, dict):
        raise ValueError('Invalid CLI receipt archive')
    metadata = receipt.get('provider')
    selection = 'explicit' if expected.model else 'cli-default'
    if (type(receipt.get('schema')) is not int or receipt['schema'] != 1
            or receipt.get('transport') != 'cli' or receipt.get('cli_call') is not True
            or receipt.get('http_call') is not False or receipt.get('model') != expected.model
            or not isinstance(metadata, dict) or metadata.get('runner') != expected.runner
            or metadata.get('model_selection') != selection
            or type(metadata.get('exit_code')) is not int or metadata['exit_code'] != 0):
        raise ValueError('CLI receipt identity or completion mismatch')
    if (not isinstance(request, dict) or set(request) != {'system', 'user', 'response_schema'}
            or not isinstance(request['system'], str) or not isinstance(request['user'], str)
            or not (request['response_schema'] is None or isinstance(request['response_schema'], dict))
            or not isinstance(response, str) or not response.strip()):
        raise ValueError('Invalid CLI request or response archive')
    request_hash = _digest(json.dumps(request, ensure_ascii=False, sort_keys=True))
    if (receipt.get('request_sha256') != request_hash
            or receipt.get('response_sha256') != _digest(response)):
        raise ValueError('CLI request or response hash mismatch')
    prompt = build_prompt(request['system'], request['user'], request['response_schema'])
    if not isinstance(prompt, str) or metadata.get('prompt_sha256') != _digest(prompt):
        raise ValueError('CLI prompt hash mismatch')
    path = _stdout_file(calls, metadata.get('stdout_path'))
    try:
        stdout = path.read_bytes().decode('utf-8')
    except (OSError, UnicodeError) as exc:
        raise ValueError('CLI stdout archive is missing or unreadable') from exc
    if metadata.get('stdout_sha256') != _digest(stdout):
        raise ValueError('CLI stdout hash mismatch')
    try:
        decoded, provider = decode_stdout(expected.runner, stdout)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError('CLI stdout does not contain a completed response') from exc
    if (not isinstance(decoded, str) or decoded != response
            or _digest(decoded) != receipt.get('response_sha256')
            or provider != metadata.get('provider')):
        raise ValueError('CLI decoded response or provider metadata mismatch')
    return {'runner': expected.runner, 'model': expected.model, 'model_selection': selection,
            'producer': expected.label, 'stdout_sha256': metadata['stdout_sha256']}
