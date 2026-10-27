"""Explicit HTTP comparison checkpoints and recorded-answer replay adapters.

Normal CLI execution never substitutes these for a failing live call.
Receipt verification, cache keys and candidate order remain with their owners.
"""
from dataclasses import dataclass
from pathlib import Path

from . import answer_cache
from .design_types import UnitResult


def open_archive(cfg, enabled):
    if not enabled:
        return None
    from .design_replay import Archive
    return Archive(cfg.build_dir / 'prompts/calls', cfg.agent)


def replay_unit(archive, system, user, schema, tag, topic, validate):
    if archive:
        for record in archive.candidates(system, user, schema, tag):
            try:
                statements = validate(record['raw'], archive.reviewer)
                provenance = {key: record[key] for key in
                              ('receipt', 'request_sha256', 'response_sha256')} | {
                                  'topic': topic['id'], 'part': topic.get('_part_id')}
                return UnitResult(statements, provenance)
            except (ValueError, TypeError, KeyError):
                continue  # Rejected old output never consumes a live retry.
    return None


@dataclass(frozen=True)
class AnswerCheckpoint:
    path: Path | None
    response: str | None

    def save(self, response):
        answer_cache.save(self.path, response)


def checkpoint(cfg, model, system, user, options, focused_system, unit_policy):
    path = answer_cache.checkpoint(cfg, model.meta.get('source_commit'), system, user,
        {'request': options, **({'policy': unit_policy} if focused_system is not None else {}),
         'revision': cfg.review.design_revision})
    return AnswerCheckpoint(path, answer_cache.read(path))
