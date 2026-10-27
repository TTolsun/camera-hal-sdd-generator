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
from .design_request import prepare_requests, _design_units
from .design_execution import _request_unit, _UnitRejected
from .design_types import DesignResult
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
    return DesignResult(pinned, resolved, report, artifact)



def generate(cfg, model, agent, section, previous=None, *, replay_http=False, all_design_units=False):
    plan, answers, origins = _prepare_generation(cfg, model, section, previous)
    reused = list(answers)
    units = _design_units(section, answers)
    replayed, failures = [], []
    archive = None
    if replay_http:
        from .design_replay import Archive
        archive = Archive(cfg.build_dir / 'prompts/calls', cfg.agent)
    for topic in units:
        try:
            statements, record = _request_unit(cfg, model, agent, section, topic,
                plan.prompts[topic['id']], plan.policy['design_grounding'], archive, answers)
        except _UnitRejected as exc:
            if not all_design_units:
                raise ValueError(str(exc)) from None
            failures.append(str(exc))
            continue
        answers.setdefault(topic['id'], []).extend(statements)
        if record is not None:
            replayed.append(record)
    if failures:
        raise ValueError('\n'.join(failures))
    return _assemble_generation(cfg, model, section, answers, plan.inputs, reused, replayed, origins, plan.policy)



def verify(model, section, manuscript):
    from .document_metadata import split_frontmatter
    meta, body = split_frontmatter(manuscript)
    artifact = meta.get('generated_design')
    if isinstance(artifact, dict) and artifact.get('grounding_review') == 'passed':
        from .grounding import policy_hash
        current = policy_hash()
        allowed = {current}
        origins, answers = artifact.get('topic_agents'), artifact.get('answers')
        # Never infer HTTP origin from a missing or mixed producer map. Every
        # answer must have an explicit HTTP producer before accepting the alias.
        if (isinstance(answers, dict) and answers and isinstance(origins, dict)
                and set(origins) == set(answers)
                and all(isinstance(value, str) and value.partition('/')[0] in _HTTP_PROVIDERS
                        and value.partition('/')[2] for value in origins.values())):
            allowed.add(_http_grounding_policy(current))
        recorded_policy = artifact.get('grounding_policy')
        if not isinstance(recorded_policy, str) or recorded_policy not in allowed:
            raise ValueError('근거 대조 정책이 바뀌었습니다. 실제 모델로 다시 검증·생성해야 합니다.')
    if not isinstance(artifact, dict) or artifact.get('schema') != 1:
        raise ValueError('LLM 설계 답변 기록이 없거나 형식이 잘못되었습니다.')
    if artifact.get('input_fingerprint') != fingerprint(model, section):
        raise ValueError('LLM 설계 입력 근거·질문이 변경되어 재생성이 필요합니다.')
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
        if all(f"## {topic['title']}\n\n{candidate}" not in body for candidate in (text, legacy)):
            raise ValueError('LLM 설계 답변이 원고에 없습니다.')
    return report

