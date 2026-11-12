"""One exact checkpoint identity shared by planning and actual execution."""
import json

from .cli_checkpoint import checksum, same_request_context
from .design_request import _unit_request
from .design_response import response_schema
from .llm import AgentError
from .state_io import save
from .trial_workspace import reject_symlinks
from .validation_stage import current, load_json

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
    return checkpoints.UnitStore(cfg, identity, comparison_scope=(
        'design', section['id'], topic['id'], topic.get('_part_id'), topic.get('_subpart_id'))), identity


def changes(previous, current):
    grounding = previous.get('grounding_policy') != current.get('grounding_policy')
    validation = any(previous.get(key) != current.get(key) for key in
                     ('validation_policy', 'validation_model', 'validation_answers'))
    validation = validation or (previous.get('topic', {}).get('answer_contract') !=
                                 current['topic'].get('answer_contract'))
    return grounding, validation


class PendingReview:
    """A receipt for a draft whose grounding transport failed, without a verdict."""

    def __init__(self, store):
        self.store = store
        identity = checksum(dict(inputs=store.identity, scope=store.comparison_scope))
        self.path = store.cfg.build_dir / 'cli-pending-reviews' / f'{identity}.json'

    def _record(self, name):
        record, = self.store._records([name])
        request = self.store.identity['request']
        if (record.request['system'] != request['system']
                or record.request.get('response_schema') != request['response_schema']
                or not same_request_context(request['user'], record.request['user'])):
            raise ValueError('pending draft does not match the current CLI request')
        return record

    def read(self):
        if not self.path.exists():
            return None
        try:
            reject_symlinks(self.path)
            data = load_json(self.path)
            payload = data['payload']
            if data['sha256'] != checksum(payload) or payload['input_sha256'] != self.path.stem:
                raise ValueError('pending draft identity or checksum mismatch')
            name = payload['receipt']
            if name is not None:
                return self._record(name).raw, self.store.calls / name
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ValueError(f'CLI pending review is damaged; previous output preserved: {self.path}: {exc}') from exc
        return None

    def write(self, receipt):
        """Save the draft receipt, or consume it before making a fresh review call."""
        try:
            name = None
            if receipt is not None:
                name = receipt.resolve().relative_to(self.store.calls.resolve()).as_posix()
                self._record(name)
            payload = dict(input_sha256=self.path.stem, receipt=name)
            data = dict(payload=payload, sha256=checksum(payload))
            reject_symlinks(self.path)
            inputs = current()
            if inputs is not None:
                inputs.verify()
            save(self.path, data, newline='\n')
            if inputs is not None:
                inputs.produced(self.path, (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode())
        except (ValueError, OSError) as exc:
            raise AgentError(f'CLI pending review persistence failed; previous output preserved: {exc}') from exc
