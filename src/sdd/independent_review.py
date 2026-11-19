"""Schedule independent work and reuse validated verdicts for exact question inputs."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import islice
import json

from .call_records import canonical_request_hash
from .change_review import change_review_instructions
from .cli_checkpoint import Capture, UnitStore, execution_identity
from .cli_schema import validate_original
from .review_quality import KOREAN_REVIEW_INSTRUCTIONS, validate_korean_review


def schedule_reviews(function, items, *, workers=1):
    """Run isolated calls with at most workers in flight and return results in input order."""
    if workers < 1:
        raise ValueError('workers must be at least 1')
    if workers == 1:
        return [function(item) for item in items]

    items = iter(items)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        slots = workers
        try:
            while True:
                for item in islice(items, slots):
                    pending[pool.submit(function, item)] = len(results)
                    results.append(None)
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    results[pending.pop(future)] = future.result()
                slots = len(done)
        finally:
            for future in pending:
                future.cancel()
    return results


def review_workspace(cfg):
    return cfg.build_dir / 'review-prompts'


def review_unit(cfg, execution, key, request, validate, *, policy, change_sources=None,
                korean_candidate=None):
    """Return the current verdict and its original native receipt provenance."""
    if cfg.agent.kind != 'cli' or not cfg.agent.model:
        raise ValueError('Independent review requires a selected CLI and explicit model')
    if korean_candidate is not None:
        if not isinstance(korean_candidate, str):
            raise ValueError('Korean review requires the exact candidate text')
        candidate_json = json.dumps(korean_candidate, ensure_ascii=False)
        user = request['user']
        if korean_candidate not in user and candidate_json not in user:
            user = '검토 대상 원고 원문\n' + candidate_json + '\n' + user
        request = dict(request, user=KOREAN_REVIEW_INSTRUCTIONS + '\n' + user)
    if change_sources is not None:
        prefix = change_review_instructions(*change_sources)
        if prefix:
            request = dict(request, user=prefix + '\n' + request['user'])

    def check(raw):
        checked = validate(raw)
        if korean_candidate is not None:
            validate_korean_review(json.loads(raw), korean_candidate)
        return checked

    schema = request['response_schema']
    identity = dict(purpose='independent-question-review', policy=policy, request=request,
                    execution=execution_identity(cfg.agent, schema))
    if korean_candidate is not None:
        identity['korean_candidate_sha256'] = canonical_request_hash({'candidate': korean_candidate})
    # Keep independent review units in a stable workspace across attempt IDs.
    store = UnitStore(cfg, identity, calls=review_workspace(cfg) / 'calls')
    execution.unit(key, 'running')
    cached = store.read()
    if cached is None:
        capture = Capture(execution)
        raw = capture.chat(request['system'], request['user'], tag=key, response_schema=schema)
        validate_original(raw, schema)
        checked = check(raw)
        store.write(raw, checked, capture)
        completed = store.read()
        if completed is None:
            raise ValueError('Independent review lacks a completed native CLI receipt')
    else:
        completed = cached
    saved, reviewer = completed
    raw = reviewer.chat(request['system'], request['user'], response_schema=schema)
    checked = check(raw)
    if saved['raw'] != raw or saved['statements'] != checked:
        raise ValueError('Independent review checkpoint differs from the exact CLI verdict')
    origin = dict(request_sha256=canonical_request_hash(request), receipts=saved['receipts'],
                  status='checkpoint-reused' if cached is not None else 'completed')
    execution.unit(key, origin['status'], request_sha256=origin['request_sha256'], receipts=origin['receipts'])
    return checked, origin
