"""Orchestrate generation, manuscript assembly and publication revalidation.

The response and execution modules retain the existing public function exports.
No path records human approval.
"""
from __future__ import annotations

from . import duplicates
from .evidence import fingerprint, contract_text
from .design_response import (
    enabled, preflight, digest, quote_text, source_passages, resolve_passages,
    response_schema, materialize, source_names, normalize_answer, validate_answers,
    decode_unit, _validate_retained,
)
from .design_request import prepare_requests, _design_units, _unit_request, _unit_tag
from .design_execution import _request_unit, _UnitRejected, _validate_unit_response
from .design_types import DesignResult
from .design_trials import open_archive
from .design_compat import allowed_policies
from .design_compat import (
    HTTP_PROVIDERS as _HTTP_PROVIDERS,
    HTTP_GROUNDING_SCHEMA_COMPATIBILITY as _HTTP_GROUNDING_SCHEMA_COMPATIBILITY,
    http_grounding_policy as _http_grounding_policy,
)


def _prepare_generation(cfg, model, section, previous):
    preflight(model, section)
    if cfg.agent.kind == 'dry-run':
        raise ValueError(f"{section['id']}: 필수 LLM 답변은 dry-run으로 생성할 수 없습니다.")
    plan = prepare_requests(cfg, model, section, previous)
    from .design_reuse import reusable
    answers, origins = reusable(model, section, plan.previous, plan.inputs, _validate_retained)
    for tid in duplicates.repeated_topics(model, section, answers):
        answers.pop(tid), origins.pop(tid, None)
    return plan, answers, origins


def _assemble_generation(cfg, model, section, answers, inputs, reused, replayed, origins, policy):
    pinned, resolved, report = validate_answers(model, section, answers)
    artifact = {'schema': 1, 'input_fingerprint': fingerprint(model, section), 'answers': answers,
                'topic_inputs': inputs, 'reused_topics': reused, 'replayed_units': replayed,
                'generated_topics': [t['id'] for t in section['design_topics'] if t['id'] not in reused],
                'topic_agents': {tid: origins.get(tid, cfg.agent.label) for tid in answers},
                'grounding_review': 'passed' if policy['design_grounding'] else 'not-run',
                'grounding_policy': policy.get('grounding_policy')}
    if section.get('reader_scope'):
        artifact['reader_scope'] = section['reader_scope']
    if cfg.agent.kind == 'cli':
        from .cli_checkpoint import validation_policy, validation_model, style_policy
        artifact['validation_policy'] = validation_policy()
        artifact['validation_model'] = validation_model(model)
        artifact['style_policy'] = style_policy(cfg)
    return DesignResult(pinned, resolved, report, artifact)


def generate(cfg, model, agent, section, previous=None, *, replay_http=False, all_design_units=False):
    from .generation_run import Execution
    execution = agent if isinstance(agent, Execution) else Execution(cfg, agent)
    keys = [_unit_tag(section, unit) for unit in _design_units(section, {})]
    with execution.document(section['id'], keys):
        return _generate(cfg, model, execution, section, previous,
                         replay_http=replay_http, all_design_units=all_design_units)


def _generate(cfg, model, agent, section, previous=None, *, replay_http=False, all_design_units=False):
    plan, answers, origins = _prepare_generation(cfg, model, section, previous)
    topic_prompts, policy, inputs = plan.prompts, plan.policy, plan.inputs
    reused = list(answers)
    for unit in _design_units(section, {}):
        if unit['id'] in answers:
            agent.unit(_unit_tag(section, unit), 'manuscript-reused')
    units = _design_units(section, answers)
    replayed, resumed, failures = [], [], []
    archive = open_archive(cfg, replay_http)
    for topic in units:
        key = _unit_tag(section, topic)
        try:
            agent.check_time()
            statements, record = _request_unit(cfg, model, agent, section, topic,
                topic_prompts[topic['id']], policy['design_grounding'], archive, answers)
        except _UnitRejected as exc:
            agent.unit(key, 'failed', error=str(exc))
            if not all_design_units:
                raise ValueError(str(exc)) from None
            failures.append(str(exc))
            continue
        except BaseException as exc:
            from .generation_run import failure_kind
            agent.unit(key, 'failed', error=str(exc), failure_kind=failure_kind(exc))
            raise
        answers.setdefault(topic['id'], []).extend(statements)
        if record is not None and 'checkpoint' in record:
            resumed.append(record)
            agent.unit(key, 'checkpoint-revalidated' if record.get('revalidated') else 'checkpoint-reused')
        elif record is not None:
            replayed.append(record)
            agent.unit(key, 'replayed')
        else:
            agent.unit(key, 'newly-generated')
    if failures:
        raise ValueError('\n'.join(failures))
    result = _assemble_generation(cfg, model, section, answers, inputs, reused, replayed, origins, policy)
    if reused and previous:
        from .document_metadata import split_frontmatter
        old_meta, _ = split_frontmatter(previous)
        result[3]['reuse_lineage'] = dict(source_commit=old_meta.get('source_commit'),
            body_sha256=old_meta.get('generated_design', {}).get('body_sha256'),
            topics=list(reused), validation='current source, contract and editorial checks; human review pending')
    if resumed:
        result[3]['checkpoint_units'] = resumed
    return result


def verify(model, section, manuscript, *, cfg=None):
    if cfg is not None:
        from .reader_profiles import family_errors
        options = cfg.documentation.settings()
        if errors := family_errors(cfg.sections(), options.get('features', []), enabled=options.get('enabled', False)):
            raise ValueError('\n'.join(errors))
    from .document_metadata import split_frontmatter
    meta, body = split_frontmatter(manuscript)
    artifact = meta.get('generated_design')
    if isinstance(artifact, dict) and cfg is not None and 'style_policy' in artifact:
        from .cli_checkpoint import style_policy
        if artifact['style_policy'] != style_policy(cfg):
            raise ValueError('집필 규칙 정책이 바뀌었습니다. 관련 원고를 다시 검토·생성해야 합니다.')
    if isinstance(artifact, dict) and artifact.get('grounding_review') == 'passed':
        from .grounding import policy_hash
        current = policy_hash()
        allowed = allowed_policies(current, artifact)
        recorded_policy = artifact.get('grounding_policy')
        if not isinstance(recorded_policy, str) or recorded_policy not in allowed:
            raise ValueError('근거 대조 정책이 바뀌었습니다. 실제 모델로 다시 검증·생성해야 합니다.')
    if not isinstance(artifact, dict) or artifact.get('schema') != 1:
        raise ValueError('LLM 설계 답변 기록이 없거나 형식이 잘못되었습니다.')
    if artifact.get('input_fingerprint') != fingerprint(model, section):
        raise ValueError('LLM 설계 입력 근거·질문이 변경되어 재생성이 필요합니다.')
    if artifact.get('reader_scope') != section.get('reader_scope'):
        raise ValueError('LLM 원고의 독자 범위 기록이 현재 계약과 다릅니다.')
    if artifact.get('body_sha256') != digest(body.strip()):
        raise ValueError('LLM 설계 답변 기록과 원고 본문이 일치하지 않습니다.')
    # 게시 검증에서는 중복 문장 검사를 경고로만 둔다. 이미 만든 원고를 나중에 생긴 휴리스틱으로 막지 않고, 생성할 때와
    # 영향 분석(sdd impact --config-changes)에서 다시 쓰도록 알린다.
    pinned, resolved, report = validate_answers(model, section, artifact.get('answers'), enforce_repeats=False)
    if getattr(pinned, 'repeated_findings', None):
        report['repeated_sentences'] = list(pinned.repeated_findings)
    from .visuals import strip_blocks
    body = strip_blocks(body)
    for topic in resolved['design_topics']:
        text, _ = contract_text(pinned, section['id'], topic)
        legacy, _ = contract_text(pinned, section['id'], topic, grouped=False)
        from .product_context import scope_notice
        if all(f"## {topic['title']}\n\n{scope_notice(topic)}{candidate}" not in body for candidate in (text, legacy)):
            raise ValueError('LLM 설계 답변이 원고에 없습니다.')
    return report

