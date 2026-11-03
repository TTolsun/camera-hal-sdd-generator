"""Revalidate literal catalog values against completed native CLI call archives."""
import hashlib
import json
import re
from pathlib import Path

from .call_records import iter_records
from .cli_provenance import verify_cli_receipt
from .translation import (_batch_schema, _batch_system, _single_schema,
                          _single_system, _single_retry_system, _validate_text, _retry_feedback,
                          _batch_values, _single_value)
from .translation_context import matches_archive, for_source


def _next_retry(payload, raw, *, batch):
    """Derive exactly the feedback and remaining input of a real failed unit."""
    sources = payload['texts'] if batch else {'source':payload['source']}
    pending, errors, values = {}, [], {}
    try:
        values = _batch_values(raw, sources) if batch else {'source':_single_value(raw)}
    except (ValueError, TypeError, KeyError) as exc:
        pending, errors = dict(sources), [str(exc)]
    else:
        for key, source in sources.items():
            try:
                _validate_text(source, values[key])
            except (ValueError, TypeError, KeyError) as exc:
                pending[key] = source
                errors.append(f'Translation ID {key}: {exc}' if batch else str(exc))
    if not pending:
        return None, values
    if batch:
        next_payload = {'texts':pending}
        context = {key:value for key,value in payload.get('read_only_context', {}).items() if key in pending}
        if context:
            next_payload['read_only_context'] = context
    else:
        next_payload = payload
    user = json.dumps(next_payload, ensure_ascii=False) + _retry_feedback(' / '.join(errors), batch=batch)
    return (user, (_batch_schema(pending) if batch else _single_schema())), values


def verified_catalog_units(agent, catalog, archives, *, allow_other_values=False, batch_only=False,
                           instruction_strings=None):
    """Return existing values with exact text, context, instruction and CLI proof.

    This performs no model call and grants no semantic or human approval. A
    different runner/model, changed instruction/context or unproven value is
    simply ineligible for reuse. Broken selected-runner receipts fail closed.
    Prefilling a changed run should use batch_only: single-call known_terms
    belong to that call's original glossary snapshot, unlike independent batch
    units. Current single-call outputs/checkpoints can still be authenticated.
    Migration can require the current catalog's instruction flags while still
    checking an old call against its original source/context via catalog.
    """
    if agent.kind != 'cli' or not agent.model:
        raise ValueError('Catalog reuse requires an explicit CLI model')
    policy_strings = catalog['strings'] if instruction_strings is None else instruction_strings
    batch_system = _batch_system(policy_strings)
    single_system = _single_system(policy_strings)
    retry_system = _single_retry_system(policy_strings)
    result = {}
    for calls in sorted({Path(root).resolve() for root in archives}):
        if not calls.exists():
            continue
        successors = {}
        records = sorted(iter_records(calls), key=lambda row:
                         (str(row.receipt_path.parent), int(row.receipt_path.name.split('.')[0])))
        for record in records:
            receipt, request = record.receipt, record.request
            tag = re.fullmatch(r'translation_(batch_)?(\d+)_(\d+)', receipt.get('tag', ''))
            if (not tag
                    or receipt.get('transport') != 'cli' or receipt.get('model') != agent.model
                    or receipt.get('provider', {}).get('runner') != agent.runner):
                continue
            payload, end = json.JSONDecoder().raw_decode(request['user'])
            if not isinstance(payload, dict):
                continue
            batch, offset, attempt = bool(tag[1]), tag[2], int(tag[3])
            if batch_only and not batch:
                continue
            chain_key = (record.receipt_path.parent, batch, offset, attempt)
            predecessor = successors.get(chain_key)
            if attempt:
                if predecessor is None or predecessor['request'] != request:
                    continue
            elif request['user'][end:]:
                continue
            history = predecessor['history'] if attempt else []
            if 'texts' in payload:
                sources = payload['texts']
                if (not batch or set(payload) - {'texts', 'read_only_context'} or request['system'] != batch_system
                        or request['response_schema'] != _batch_schema(sources)):
                    continue
            elif 'source' in payload:
                sources = {'source':payload['source']}
                if (batch or set(payload) - {'source', 'known_terms', 'read_only_context'}
                        or request['system'] != (retry_system if attempt else single_system)
                        or request['response_schema'] != _single_schema()):
                    continue
            else:
                continue
            proof = verify_cli_receipt(request, record.raw, receipt, calls, agent)
            following, values = _next_retry(payload, record.raw, batch=batch)
            if following:
                user, schema = following
                origin = dict(receipt=str(record.receipt_path),
                    receipt_sha256=hashlib.sha256(record.receipt_path.read_bytes()).hexdigest(),
                    request_sha256=receipt['request_sha256'], response_sha256=receipt['response_sha256'])
                successors[(record.receipt_path.parent, batch, offset, attempt+1)] = dict(
                    request=dict(system=batch_system if batch else retry_system, user=user, response_schema=schema),
                    history=[*history, origin])
            for key, source in sources.items():
                if (source not in catalog['strings']
                        or not matches_archive({'request':request}, key, catalog, source)):
                    continue
                try:
                    value = _validate_text(source, values[key])
                except (ValueError, TypeError, KeyError):
                    continue
                if not allow_other_values and value != catalog['strings'][source]:
                    continue
                context = json.dumps(for_source(catalog, source), ensure_ascii=False, sort_keys=True)
                completed = receipt.get('completed_at', '')
                if source in result and result[source]['completed_at'] > completed:
                    continue
                result[source] = dict(proof, receipt=str(record.receipt_path), completed_at=completed,
                    receipt_sha256=hashlib.sha256(record.receipt_path.read_bytes()).hexdigest(),
                    request_sha256=receipt['request_sha256'], response_sha256=receipt['response_sha256'],
                    context_sha256=hashlib.sha256(context.encode()).hexdigest(),
                    translation_sha256=hashlib.sha256(value.encode()).hexdigest(),
                    reused_value=value, retry_chain=history, native_call=False, human_review='pending')
    return result
