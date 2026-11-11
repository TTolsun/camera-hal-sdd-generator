"""Reuse validated independent verdicts for the exact same question input."""
from .call_records import canonical_request_hash
from .cli_checkpoint import Capture, UnitStore, execution_identity
from .cli_schema import validate_original


def review_workspace(cfg):
    return cfg.build_dir / 'review-prompts'


def review_unit(cfg, execution, key, request, validate, *, policy):
    """Return the current verdict and its original native receipt provenance."""
    if cfg.agent.kind != 'cli' or not cfg.agent.model:
        raise ValueError('Independent review requires a selected CLI and explicit model')
    schema = request['response_schema']
    identity = dict(purpose='independent-question-review', policy=policy, request=request,
                    execution=execution_identity(cfg.agent, schema))
    # Keep independent review units in a stable workspace across attempt IDs.
    store = UnitStore(cfg, identity, calls=review_workspace(cfg) / 'calls')
    execution.unit(key, 'running')
    cached = store.read()
    if cached is None:
        capture = Capture(execution)
        raw = capture.chat(request['system'], request['user'], tag=key, response_schema=schema)
        validate_original(raw, schema)
        checked = validate(raw)
        store.write(raw, checked, capture)
        completed = store.read()
        if completed is None:
            raise ValueError('Independent review lacks a completed native CLI receipt')
    else:
        completed = cached
    saved, reviewer = completed
    raw = reviewer.chat(request['system'], request['user'], response_schema=schema)
    checked = validate(raw)
    if saved['raw'] != raw or saved['statements'] != checked:
        raise ValueError('Independent review checkpoint differs from the exact CLI verdict')
    origin = dict(request_sha256=canonical_request_hash(request), receipts=saved['receipts'],
                  status='checkpoint-reused' if cached is not None else 'completed')
    execution.unit(key, origin['status'], request_sha256=origin['request_sha256'], receipts=origin['receipts'])
    return checked, origin
