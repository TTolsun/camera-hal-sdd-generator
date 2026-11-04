"""Execute one unit with the existing bounded draft/review retry budget."""
from __future__ import annotations

from . import duplicates
from .design_response import decode_unit, response_schema
from .design_request import _unit_request, _unit_tag
from .design_types import TopicPrompt, UnitResult
from .llm import SCHEMA_KINDS
from .design_trials import replay_unit, checkpoint


def _validate_unit_response(cfg, model, agent, section, topic, raw, sources, passages, tag,
                            grounding, source_files, scopes, context_records, *, reviewer=None, prior_answers=None):
    statements = decode_unit(model, section, topic, raw, sources, passages)
    if prior_answers is not None:
        prior = {tid: list(values) for tid, values in prior_answers.items()}
        repeated = duplicates.statement_findings(
            model, section['id'], {**prior, topic['id']: prior.get(topic['id'], []) + statements},
            only_after={**{tid: len(v) for tid, v in prior.items()}, topic['id']: len(prior.get(topic['id'], []))},
            summaries=duplicates.summary_keys(section))
        if repeated:
            raise ValueError(' / '.join(repeated))
    if grounding:
        from .grounding import review as check_grounding
        # The existing grounding consumer needs only configuration and chat.
        from types import SimpleNamespace
        check_grounding(SimpleNamespace(cfg=cfg, agent=reviewer(agent) if reviewer else agent),
                        topic, statements, sources, tag,
                        source_files=source_files, source_scopes=scopes, context_records=context_records)
    return statements


class _UnitRejected(ValueError):
    """Exhausted response validation, eligible for all-design-units collection."""

    def __init__(self, message, *, category=None):
        self.category = category
        super().__init__(message)


def _request_unit(cfg, model, agent, section, topic, prompt, grounding, archive, answers):
    focused_system, system, unit_policy = TopicPrompt(*prompt)
    request = _unit_request(model, section, topic, focused_system)
    sources, source_files = request.sources, request.source_files
    context_records, scopes = request.context_records, request.scopes
    passages, base_user = request.passages, request.user
    tag = _unit_tag(section, topic)
    schema = response_schema(topic, passages) if cfg.agent.kind in SCHEMA_KINDS else None
    from .grounding import GroundingFormatError, policy_hash
    from .repair_diagnostics import ReviewAttempt, UnchangedRejectedReview, observe_attempt, rejected_reviews
    profile = dict(kind=cfg.agent.kind, runner=cfg.agent.runner, model=cfg.agent.model,
                   command=cfg.agent.identity_command, args=cfg.agent.args,
                   grounding_policy=policy_hash() if grounding else None)
    diagnostic_context = dict(section=section['id'], topic=topic, sources=sources,
                              scopes=scopes, source_commit=model.meta.get('source_commit'),
                              system=system, unit_policy=unit_policy, profile=profile)
    rejected = rejected_reviews(tag, diagnostic_context)
    pending_checkpoint_raw, carried_receipts = None, []
    store = None
    if cfg.agent.kind == 'cli' and cfg.agent.model and cfg.review.cli_checkpoint:
        from .cli_checkpoint import Capture
        from .design_checkpoint import store_for
        store, identity = store_for(cfg, model, section, topic, prompt, grounding, answers, schema=schema)
        agent.unit(tag, 'running', input_sha256=store.path.stem,
                   dependencies={key: value for key, value in identity.items() if key not in ('request', 'topic')})
        cached_unit = store.read()
        if cached_unit is not None:
            saved, reviewer = cached_unit
            from .design_checkpoint import changes
            grounding_changed, validation_changed = changes(saved['identity'], identity)
            review_agent = Capture(agent) if grounding_changed else reviewer
            checkpoint_review = ReviewAttempt(review_agent, rejected, profile) if grounding_changed else None
            try:
                statements = _validate_unit_response(cfg, model, review_agent, section, topic,
                    saved['raw'], sources, passages, tag, grounding, source_files, scopes,
                    context_records, prior_answers=answers,
                    reviewer=(lambda _: checkpoint_review) if checkpoint_review else None)
            except BaseException as exc:
                if checkpoint_review is not None:
                    category = ('review-agent-failure' if checkpoint_review.failed else
                                'review-format' if isinstance(exc, GroundingFormatError) else
                                'verdict-conflict-risk' if isinstance(exc, UnchangedRejectedReview) else
                                'semantic' if checkpoint_review.returned and isinstance(exc, ValueError) else
                                'deterministic-validation')
                    observe_attempt(tag, 'design', 'checkpoint-revalidation', context=diagnostic_context,
                        raw=saved['raw'], category=category, error=exc, receipt=checkpoint_review.receipt,
                        action='Keep a structurally valid checkpoint for a malformed-verdict-only retry; otherwise repair the identified claim/source before another review.',
                        details={'review_request_sha256': checkpoint_review.request} if category == 'semantic' else None)
                    if category == 'semantic':
                        rejected[checkpoint_review.request] = str(exc)
                    if checkpoint_review.failed:
                        raise
                    if isinstance(exc, GroundingFormatError):
                        pending_checkpoint_raw = saved['raw']
                        carried_receipts = [store.calls/name for name in saved['receipts']] + review_agent.receipts
                if not isinstance(exc, (ValueError, TypeError, KeyError)):
                    raise
                if not (grounding_changed or validation_changed):
                    raise
                # A changed policy never inherits an obsolete pass. Only this
                # rejected unit is drafted again, within the same run budget.
                statements = None
                agent.unit(tag, 'revalidation-rejected', error=str(exc))
            if statements is not None:
                if statements != saved['statements'] and not (grounding_changed or validation_changed):
                    raise ValueError('CLI checkpoint validated statements mismatch')
                receipt_names = saved['receipts']
                if grounding_changed or validation_changed:
                    capture = Capture(agent)
                    capture.receipts = [store.calls/name for name in saved['receipts']]
                    if grounding_changed:
                        capture.receipts += review_agent.receipts
                    store.write(saved['raw'], statements, capture)
                    receipt_names = [path.resolve().relative_to(store.calls.resolve()).as_posix()
                                     for path in capture.receipts]
                if checkpoint_review is not None:
                    observe_attempt(tag, 'design', 'checkpoint-revalidation', context=diagnostic_context,
                        raw=saved['raw'], receipt=checkpoint_review.receipt, status='accepted-current-checks',
                        action='Current checkpoint revalidation passed; preserve its original generation provenance.')
                return UnitResult(statements, dict(checkpoint=store.path.name, topic=topic['id'],
                                        part=topic.get('_part_id'), subpart=topic.get('_subpart_id'),
                                        revalidated=grounding_changed or validation_changed,
                                        new_grounding_review=grounding_changed,
                                        receipts=receipt_names))
        agent = Capture(agent)
        agent.receipts = carried_receipts
    replayed = replay_unit(archive, system, base_user, schema, tag, topic,
        lambda raw, reviewer: _validate_unit_response(cfg, model, agent,
            section, topic, raw, sources, passages, tag + '_replay',
            grounding, source_files, scopes, context_records, reviewer=reviewer, prior_answers=answers))
    if replayed is not None:
        return replayed
    user = base_user
    last, last_category = None, None
    options = {'response_schema': response_schema(topic, passages)} if cfg.agent.kind in SCHEMA_KINDS else {}
    saved = checkpoint(cfg, model, system, base_user, options, focused_system, unit_policy)
    cached = saved.response
    pending_raw = pending_checkpoint_raw
    drafted_live = False
    for attempt in range(cfg.max_retries + 1):
        if len(system) + len(user) > cfg.agent.max_input_chars:
            raise ValueError(f"{section['id']}/{topic['id']}: 필수 근거 입력이 예산을 초과했습니다. 근거를 생략하지 않습니다.")
        # Ollama supports constrained JSON; generic compatible gateways still
        # use the portable prompt + parser/validator and need no schema API.
        review_retry = pending_raw is not None
        from_cache = not review_retry and cached is not None and attempt == 0
        raw = pending_raw if review_retry else cached if from_cache else agent.chat(
            system, user, tag=f"{tag}_{attempt}", **options)
        drafted_live |= not review_retry and not from_cache
        if not review_retry and not from_cache and cfg.review.design_revision:
            revision = user + '\nDraft to check (untrusted, not evidence):\n' + raw + (
                '\nRevise this draft against the sources and the complete question. '
                'Check every claim, including function ownership, nested branch guards, negations, return values, '
                'resource lifetime and ordering. Add omitted parts of the question, remove repetition and unsupported inferences. '
                'Do not turn an API obligation into an implementation guarantee. '
                'Return the complete corrected statements JSON, not a review verdict. This revision is not approval.'
            )
            if len(system) + len(revision) > cfg.agent.max_input_chars:
                raise ValueError(f"{section['id']}/{topic['id']}: 재검토 입력이 예산을 초과했습니다. 근거를 생략하지 않습니다.")
            raw = agent.chat(system, revision, tag=f"{tag}_{attempt}_revision", **options)
        review_attempt = ReviewAttempt(agent, rejected, profile)
        try:
            statements = _validate_unit_response(cfg, model, agent, section, topic, raw, sources, passages,
                                                 f'{tag}_{attempt}', grounding, source_files, scopes, context_records,
                                                 reviewer=lambda _: review_attempt, prior_answers=answers)
        except BaseException as exc:
            last = str(exc)
            if review_attempt.failed:
                observe_attempt(tag, 'design', attempt, context=diagnostic_context, raw=raw,
                    category='review-agent-failure', error=exc,
                    action='Inspect the original selected-agent failure; no semantic verdict was returned and no substitute is used.')
                raise
            if not isinstance(exc, (ValueError, TypeError, KeyError)):
                raise
            import json
            category = ('verdict-conflict-risk' if isinstance(exc, UnchangedRejectedReview) else
                        'review-format' if isinstance(exc, GroundingFormatError) else
                        'format' if isinstance(exc, json.JSONDecodeError) else
                        'semantic' if review_attempt.returned and isinstance(exc, ValueError) else
                        'review-format' if review_attempt.returned else 'deterministic-validation')
            last_category = category
            action = ('Skip the unchanged review; modify the rejected claim or evidence scope using the remaining existing draft attempts.'
                      if category == 'verdict-conflict-risk' else
                      'Keep the live draft and request a well-formed verdict; do not redraft.'
                      if category == 'review-format' else
                      'Repair the rejected claim against its source conditions; an identical review input is not a repair.'
                      if category == 'semantic' else
                      'Correct the reported source/contract/format violation before another draft; semantic status is unjudged.')
            observe_attempt(tag, 'design', attempt, context=diagnostic_context, raw=raw,
                category=category, error=exc, action=action, receipt=review_attempt.receipt,
                status='no-progress' if category == 'verdict-conflict-risk' else 'rejected',
                details={'review_request_sha256': review_attempt.request} if category == 'semantic' else None)
            if category == 'semantic':
                rejected[review_attempt.request] = last
            if isinstance(exc, GroundingFormatError) and not from_cache:
                # The same live draft passed all structural/source checks.
                # Revalidate it and request a fresh review on the next existing
                # attempt, without drafting or consuming a nested retry budget.
                pending_raw = raw
                continue
            pending_raw = None
            # Retry with the validation error and original evidence.
            # Standard mode also retains the last rejected draft.
            if focused_system is not None:
                # Repeating a rejected paragraph anchored small-model retries
                # to that paragraph. Keep the evidence and actionable error.
                prefix, marker, suffix = base_user.rpartition('\n출력:')
                user = (prefix + '\n작성 조건: ' + last
                        + '\n질문의 모든 조건을 근거에서 다시 확인하세요.' + marker + suffix)
            else:
                user = (base_user + '\n검사에서 거절된 이전 답변(근거가 아닌 수정 대상):\n' + raw
                        + '\n수정할 오류: ' + last
                        + '\n질문의 모든 조건을 원문과 다시 대조하고 전체 답변 JSON을 반환하세요.')
        else:
            # A persistence/integrity failure is not a semantic verdict and
            # must not poison the exact rejected-review set on resume.
            saved.save(raw)
            if store is not None:
                store.write(raw, statements, agent)
            observe_attempt(tag, 'design', attempt, context=diagnostic_context, raw=raw,
                status='accepted-current-checks', receipt=review_attempt.receipt,
                action='Continue assembly; prior observations are not automatic semantic resolution or approval.')
            if pending_checkpoint_raw is not None and not drafted_live:
                return UnitResult(statements, dict(checkpoint=store.path.name, topic=topic['id'],
                    part=topic.get('_part_id'), subpart=topic.get('_subpart_id'), revalidated=True,
                    new_grounding_review=True, receipts=[path.resolve().relative_to(store.calls.resolve()).as_posix()
                                                        for path in agent.receipts]))
            return UnitResult(statements, None)
    else:
        unit_id = f"{section['id']}/{topic['id']}" + (f"/{topic['_part_id']}" if '_part_id' in topic else '')
        failure = f"{unit_id}: LLM 답변 검증 실패: {last}"
        raise _UnitRejected(failure, category=last_category)

