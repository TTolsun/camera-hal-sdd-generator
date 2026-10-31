"""Invocation-wide limits and durable, separate call/unit outcome accounting."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections import Counter
import json
import os
import threading
import time
import uuid

from .llm import AgentError
from .state_io import save

_observed = ContextVar('sdd_observed_execution', default=None)


def observed():
    return _observed.get()


@contextmanager
def observe(cfg, phase):
    execution = _observed.get()
    if execution is not None:
        with execution.phase(phase):
            yield execution
        return
    execution = Execution(cfg, object())
    token = _observed.set(execution)
    try:
        with execution.phase(phase):
            yield execution
    finally:
        _observed.reset(token)


class BudgetExceeded(AgentError):
    pass


def failure_kind(exc):
    message = str(exc)
    if isinstance(exc, BudgetExceeded):
        return 'budget'
    if 'checkpoint' in message:
        return 'checkpoint-integrity'
    if isinstance(exc, AgentError):
        if any(term in message.lower() for term in ('usage limit', 'usage-limit', 'rate limit', 'quota', '사용량')):
            return 'cli-usage-limit'
        return 'cli-timeout' if '시간이 초과' in message else 'cli-failure'
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return 'interrupted'
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
        self._mutex = threading.RLock()
        self.operation = (cfg.raw.get('publication') or {}).get('operation_id')
        self.operation_limits = (cfg.raw.get('publication') or {}).get('budget', {})
        if (not isinstance(self.operation_limits, dict) or set(self.operation_limits) - {'max_calls', 'max_seconds'}
                or any(type(v) is not int or v < 0 for v in self.operation_limits.values())):
            raise ValueError('publication.budget accepts explicit nonnegative max_calls/max_seconds')
        if self.operation_limits and not self.operation:
            raise ValueError('publication.budget requires an operation_id across resumes')
        if self.operation is not None and (not isinstance(self.operation, str) or not self.operation.strip()):
            raise ValueError('publication.operation_id must be a nonempty string')
        self.report.update(operation_id=self.operation, operation_limits=self.operation_limits,
                           phases=[], owner_pid=os.getpid(), started_at=time.time())

    def prior(self):
        if not self.operation:
            return []
        rows = []
        for path in self.path.parent.glob('*.json'):
            if path == self.path:
                continue
            data = json.loads(path.read_bytes())
            if data.get('operation_id') == self.operation:
                rows.append(data)
        return rows

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def persist(self):
        with self._mutex:
            self.report['seconds'] = round(self.clock() - self.started, 3)
            self.report['updated_at'] = time.time()
            units = Counter(status for doc in self.report['documents'] for status in doc['units'].values())
            self.report['counts'] = dict(completed=sum(units[s] for s in ('newly-generated', 'replayed', 'completed')),
                reused=sum(units[s] for s in ('manuscript-reused', 'checkpoint-reused')),
                revalidated=units['checkpoint-revalidated'], failed=units['failed'],
                running=units['running'], not_started=units['not-started'])
            prior = self.prior()
            self.report['cumulative'] = dict(calls=len(self.report['calls'])+sum(len(r.get('calls', [])) for r in prior),
                elapsed_seconds=self.report['seconds']+sum(r.get('seconds', 0) for r in prior),
                cli_seconds=sum(c.get('seconds', 0) for r in [*prior, self.report] for c in r.get('calls', [])))
            save(self.path, self.report, newline='\n')

    @contextmanager
    def heartbeat(self, interval=30):
        stopped = threading.Event()
        errors = []
        def update():
            while not stopped.wait(interval):
                try:
                    self.persist()
                except BaseException as exc:
                    errors.append(exc)
                    break
        self.persist()
        thread = threading.Thread(target=update, name='sdd-progress', daemon=True)
        thread.start()
        try:
            yield
            if errors:
                raise RuntimeError('Progress journal failed') from errors[0]
        finally:
            stopped.set()
            thread.join()
            self.persist()

    @contextmanager
    def phase(self, name):
        row = dict(name=name, status='running', started_seconds=self.clock()-self.started)
        self.report['phases'].append(row)
        previous_phase = self.report.get('current_phase')
        self.report['current_phase'] = name
        try:
            with self.heartbeat():
                yield
            row['status'] = 'completed'
        except BaseException as exc:
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            raise
        finally:
            row['seconds'] = self.clock()-self.started-row['started_seconds']
            self.report['current_phase'] = previous_phase
            self.persist()

    @contextmanager
    def document(self, sid, units):
        row = dict(section=sid, started_seconds=self.clock()-self.started,
                   status='running', units={key: 'not-started' for key in units})
        self.current = row
        self.report['documents'].append(row)
        try:
            with self.heartbeat():
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
            self.report['current_task'] = key if status == 'running' else None
            self.current['units'][key] = status
            if details:
                self.current.setdefault('details', {})[key] = details
            self.persist()

    def check_time(self):
        elapsed = self.clock()-self.started
        if (self.operation_limits.get('max_seconds') and
                elapsed+sum(r.get('seconds', 0) for r in self.prior()) >= self.operation_limits['max_seconds']):
            raise BudgetExceeded('operation time budget exhausted; previous output preserved')
        if self.limits['max_seconds'] and elapsed >= self.limits['max_seconds']:
            raise BudgetExceeded('run time budget exhausted; previous output preserved')
        if (self.current is not None and self.limits['document_max_seconds']
                and elapsed-self.current['started_seconds'] >= self.limits['document_max_seconds']):
            raise BudgetExceeded('document time budget exhausted; previous output preserved')

    @contextmanager
    def track(self, phase):
        token = _observed.set(self)
        try:
            with self.phase(phase):
                yield
        finally:
            _observed.reset(token)

    def chat(self, system, user, **kwargs):
        from .execution_lock import lease
        if self.operation:
            import hashlib
            key = hashlib.sha256(self.operation.encode()).hexdigest()
            with lease(self.cfg, 'operation-'+key):
                return self._chat(system, user, **kwargs)
        return self._chat(system, user, **kwargs)

    def _chat(self, system, user, **kwargs):
        now = self.clock()
        calls = self.report['calls']
        remaining = []
        scopes = [(self.limits['max_calls'], len(calls), 'run call'),
                  (self.limits['max_seconds'], now-self.started, 'run time')]
        prior = self.prior()
        scopes += [(self.operation_limits.get('max_calls', 0), len(calls)+sum(len(r.get('calls', [])) for r in prior), 'operation call'),
                   (self.operation_limits.get('max_seconds', 0), now-self.started+sum(r.get('seconds', 0) for r in prior), 'operation time')]
        if self.current is not None:
            scopes += [(self.limits['document_max_calls'],
                        sum(c.get('section') == self.current['section'] for c in calls), 'document call'),
                       (self.limits['document_max_seconds'],
                        now-self.started-self.current['started_seconds'], 'document time')]
        for limit, used, label in scopes:
            if limit and used >= limit:
                raise BudgetExceeded(f'{label} budget exhausted; previous output preserved')
            if limit and label.endswith('time'):
                remaining.append(limit-used)
        row = dict(tag=kwargs.get('tag'), started_seconds=now-self.started, status='running',
                   section=self.current['section'] if self.current else None)
        calls.append(row)  # Failed transport attempts count too.
        previous_task = self.report.get('current_task')
        self.report['current_task'] = kwargs.get('tag')
        self.persist()
        timeout = self.cfg.agent.timeout_sec
        if remaining:
            self.cfg.agent.timeout_sec = min(timeout, *remaining)
        try:
            with self.heartbeat():
                raw = self.agent.chat(system, user, **kwargs)
            self.check_time()
            row['status'] = 'completed'
            return raw
        except BaseException as exc:
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            raise
        finally:
            self.cfg.agent.timeout_sec = timeout
            row['seconds'] = self.clock()-now
            self.report['current_task'] = previous_task
            self.persist()
