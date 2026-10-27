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
            only_after={**{tid: len(v) for tid, v in prior.items()}, topic['id']: len(prior.get(topic['id'], []))})
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


def _request_unit(cfg, model, agent, section, topic, prompt, grounding, archive, answers):
    focused_system, system, unit_policy = TopicPrompt(*prompt)
    request = _unit_request(model, section, topic, focused_system)
    sources, source_files = request.sources, request.source_files
    context_records, scopes = request.context_records, request.scopes
    passages, base_user = request.passages, request.user
    tag = _unit_tag(section, topic)
    schema = response_schema(topic, passages) if cfg.agent.kind in SCHEMA_KINDS else None
    store = None
    if cfg.agent.kind == 'cli' and cfg.agent.model and cfg.review.cli_checkpoint:
        from .cli_checkpoint import Capture, UnitStore, validation_policy, style_policy
        from .grounding import policy_hash
        from .cli_agent import arguments
        identity = dict(source_commit=model.meta.get('source_commit'), topic=topic,
                        request=dict(system=system, user=base_user, response_schema=schema),
                        execution=dict(runner=cfg.agent.runner, model=cfg.agent.model,
                                       command=cfg.agent.command, args=cfg.agent.args,
                                       arguments=arguments(cfg.agent, schema)),
                        prompt_policy=unit_policy, validation_policy=validation_policy(),
                        style_policy=style_policy(cfg),
                        grounding_policy=policy_hash() if grounding else None,
                        revision=cfg.review.design_revision)
        store = UnitStore(cfg, identity)
        agent.unit(tag, 'running', input_sha256=store.path.stem,
                   dependencies={key: value for key, value in identity.items() if key not in ('request', 'topic')})
        cached_unit = store.read()
        if cached_unit is not None:
            saved, reviewer = cached_unit
            grounding_changed = saved['identity'].get('grounding_policy') != identity['grounding_policy']
            validation_changed = saved['identity'].get('validation_policy') != identity['validation_policy']
            validation_changed = validation_changed or (
                saved['identity'].get('topic', {}).get('answer_contract') != topic.get('answer_contract'))
            review_agent = Capture(agent) if grounding_changed else reviewer
            try:
                statements = _validate_unit_response(cfg, model, review_agent, section, topic,
                    saved['raw'], sources, passages, tag, grounding, source_files, scopes,
                    context_records, prior_answers=answers)
            except (ValueError, TypeError, KeyError) as exc:
                if not (grounding_changed or validation_changed):
                    raise
                # A changed policy never inherits an obsolete pass. Only this
                # rejected unit is drafted again, within the same run budget.
                statements = None
                agent.unit(tag, 'revalidation-rejected', error=str(exc))
            if statements is not None:
                if statements != saved['statements']:
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
                return statements, dict(checkpoint=store.path.name, topic=topic['id'],
                                        part=topic.get('_part_id'), subpart=topic.get('_subpart_id'),
                                        revalidated=grounding_changed or validation_changed,
                                        new_grounding_review=grounding_changed,
                                        receipts=receipt_names)
        agent = Capture(agent)
    replayed = replay_unit(archive, system, base_user, schema, tag, topic,
        lambda raw, reviewer: _validate_unit_response(cfg, model, agent,
            section, topic, raw, sources, passages, tag + '_replay',
            grounding, source_files, scopes, context_records, reviewer=reviewer, prior_answers=answers))
    if replayed is not None:
        return replayed
    user = base_user
    last = None
    options = {'response_schema': response_schema(topic, passages)} if cfg.agent.kind in SCHEMA_KINDS else {}
    saved = checkpoint(cfg, model, system, base_user, options, focused_system, unit_policy)
    cached = saved.response
    from .grounding import GroundingFormatError
    pending_raw = None
    for attempt in range(cfg.max_retries + 1):
        if len(system) + len(user) > cfg.agent.max_input_chars:
            raise ValueError(f"{section['id']}/{topic['id']}: 필수 근거 입력이 예산을 초과했습니다. 근거를 생략하지 않습니다.")
        # Ollama supports constrained JSON; generic compatible gateways still
        # use the portable prompt + parser/validator and need no schema API.
        review_retry = pending_raw is not None
        from_cache = not review_retry and cached is not None and attempt == 0
        raw = pending_raw if review_retry else cached if from_cache else agent.chat(
            system, user, tag=f"{tag}_{attempt}", **options)
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
        try:
            statements = _validate_unit_response(cfg, model, agent, section, topic, raw, sources, passages,
                                                 f'{tag}_{attempt}', grounding, source_files, scopes, context_records, prior_answers=answers)
            saved.save(raw)
            if store is not None:
                store.write(raw, statements, agent)
            return UnitResult(statements, None)
        except (ValueError, TypeError, KeyError) as exc:
            last = str(exc)
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
                user = base_user.replace('\n출력:', '\n작성 조건: ' + last
                                         + '\n질문의 모든 조건을 근거에서 다시 확인하세요.\n출력:')
            else:
                user = (base_user + '\n검사에서 거절된 이전 답변(근거가 아닌 수정 대상):\n' + raw
                        + '\n수정할 오류: ' + last
                        + '\n질문의 모든 조건을 원문과 다시 대조하고 전체 답변 JSON을 반환하세요.')
    else:
        unit_id = f"{section['id']}/{topic['id']}" + (f"/{topic['_part_id']}" if '_part_id' in topic else '')
        failure = f"{unit_id}: LLM 답변 검증 실패: {last}"
        raise _UnitRejected(failure)

