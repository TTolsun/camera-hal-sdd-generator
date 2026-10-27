"""Invocation-wide limits and durable, separate call/unit outcome accounting."""
from __future__ import annotations

from contextlib import contextmanager
import time
import uuid

from .llm import AgentError
from .state_io import save


class BudgetExceeded(AgentError):
    pass


def failure_kind(exc):
    message = str(exc)
    if isinstance(exc, BudgetExceeded):
        return 'budget'
    if isinstance(exc, AgentError):
        return 'cli-timeout' if '초과' in message else 'cli-failure'
    if 'checkpoint' in message:
        return 'checkpoint-integrity'
    if '근거 대조 실패' in message:
        return 'grounding-rejected'
    return 'validation'


class Execution:
    def __init__(self, cfg, agent, *, clock=time.monotonic):
        self.cfg, self.agent, self.clock = cfg, agent, clock
        self.limits = {key: getattr(cfg.review, key) for key in
                       ('max_calls', 'max_seconds', 'document_max_calls', 'document_max_seconds')}
        for name, value in self.limits.items():
            if type(value) is not int or value < 0:
                raise ValueError(f'review.{name} must be a nonnegative integer (0 means unlimited)')
        self.started = clock()
        self.report = dict(schema=1, human_review='pending', calls=[], documents=[], limits=self.limits)
        self.path = cfg.build_dir / 'generation-runs' / (uuid.uuid4().hex + '.json')
        self.current = None

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def persist(self):
        self.report['seconds'] = round(self.clock() - self.started, 3)
        save(self.path, self.report, newline='\n')

    @contextmanager
    def document(self, sid, units):
        row = dict(section=sid, started_seconds=self.clock()-self.started,
                   status='running', units={key: 'not-started' for key in units})
        self.current = row
        self.report['documents'].append(row)
        try:
            yield
            self.check_time()
            row['status'] = 'passed'
        except BaseException as exc:
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            raise
        finally:
            row['seconds'] = self.clock()-self.started-row['started_seconds']
            self.persist()
            self.current = None

    def unit(self, key, status, **details):
        if self.current is not None:
            self.current['units'][key] = status
            if details:
                self.current.setdefault('details', {})[key] = details
            self.persist()

    def check_time(self):
        elapsed = self.clock()-self.started
        if self.limits['max_seconds'] and elapsed >= self.limits['max_seconds']:
            raise BudgetExceeded('run time budget exhausted; previous output preserved')
        if (self.current is not None and self.limits['document_max_seconds']
                and elapsed-self.current['started_seconds'] >= self.limits['document_max_seconds']):
            raise BudgetExceeded('document time budget exhausted; previous output preserved')

    def chat(self, system, user, **kwargs):
        now = self.clock()
        calls = self.report['calls']
        remaining = []
        scopes = [(self.limits['max_calls'], len(calls), 'run call'),
                  (self.limits['max_seconds'], now-self.started, 'run time')]
        if self.current is not None:
            scopes += [(self.limits['document_max_calls'],
                        sum(c.get('section') == self.current['section'] for c in calls), 'document call'),
                       (self.limits['document_max_seconds'],
                        now-self.started-self.current['started_seconds'], 'document time')]
        for limit, used, label in scopes:
            if limit and used >= limit:
                raise BudgetExceeded(f'{label} budget exhausted; previous output preserved')
            if limit and label.endswith('time'):
                remaining.append(max(1, int(limit-used)))
        row = dict(tag=kwargs.get('tag'), started_seconds=now-self.started, status='running',
                   section=self.current['section'] if self.current else None)
        calls.append(row)  # Failed transport attempts count too.
        self.persist()
        timeout = self.cfg.agent.timeout_sec
        if remaining:
            self.cfg.agent.timeout_sec = min(timeout, *remaining)
        try:
            raw = self.agent.chat(system, user, **kwargs)
            row['status'] = 'completed'
            if self.clock()-now >= self.cfg.agent.timeout_sec and remaining:
                raise BudgetExceeded('time budget exhausted; completed response not accepted')
            return raw
        except BaseException as exc:
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            raise
        finally:
            self.cfg.agent.timeout_sec = timeout
            row['seconds'] = self.clock()-now
            self.persist()
