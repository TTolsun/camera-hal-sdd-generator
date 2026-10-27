"""Small in-process contracts; manuscript schema and CLI remain unchanged."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple


class TopicPrompt(NamedTuple):
    focused_system: str | None
    system: str
    policy: str


@dataclass(frozen=True)
class UnitRequest:
    sources: dict
    source_files: dict
    context_records: dict
    scopes: dict
    passages: dict
    user: str


@dataclass(frozen=True)
class RequestPlan:
    prompts: dict[str, TopicPrompt]
    policy: dict
    inputs: dict[str, str]
    previous: str | None


class UnitResult(NamedTuple):
    statements: list[dict]
    replayed: dict | None


class DesignResult(NamedTuple):
    model: Any
    section: dict
    report: dict
    artifact: dict
