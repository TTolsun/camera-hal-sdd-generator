"""One exact checkpoint identity shared by planning and actual execution."""
from .design_request import _unit_request
from .design_response import response_schema

_UNSET = object()


def store_for(cfg, model, section, topic, prompt, grounding, answers, *, schema=_UNSET):
    if not (cfg.agent.kind == 'cli' and cfg.agent.model and cfg.review.cli_checkpoint):
        return None, None
    focus, system, unit_policy = prompt
    request = _unit_request(model, section, topic, focus)
    if schema is _UNSET:
        schema = response_schema(topic, request.passages)
    from . import cli_checkpoint as checkpoints
    from .grounding import policy_hash
    identity = dict(source_commit=model.meta.get('source_commit'), topic=topic,
        request=dict(system=system, user=request.user, response_schema=schema),
        execution=checkpoints.execution_identity(cfg.agent, schema), prompt_policy=unit_policy,
        validation_policy=checkpoints.validation_policy(), validation_model=checkpoints.validation_model(model),
        validation_answers=checkpoints.checksum(answers), style_policy=checkpoints.style_policy(cfg),
        grounding_policy=policy_hash() if grounding else None, revision=cfg.review.design_revision)
    return checkpoints.UnitStore(cfg, identity), identity


def changes(previous, current):
    grounding = previous.get('grounding_policy') != current.get('grounding_policy')
    validation = any(previous.get(key) != current.get(key) for key in
                     ('validation_policy', 'validation_model', 'validation_answers'))
    validation = validation or (previous.get('topic', {}).get('answer_contract') !=
                                 current['topic'].get('answer_contract'))
    return grounding, validation
