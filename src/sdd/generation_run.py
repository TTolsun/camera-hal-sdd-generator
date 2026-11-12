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
_cli_resume = ContextVar('sdd_cli_resume', default=None)


@contextmanager
def cli_feedback(resume_argv):
    token = _cli_resume.set(resume_argv)
    try:
        yield
    finally:
        _cli_resume.reset(token)


def observed():
    return _observed.get()


@contextmanager
def observe(cfg, phase, model=None):
    execution = _observed.get()
    if execution is not None:
        with execution.phase(phase):
            yield execution
        return
    execution = Execution(cfg, object(), model=model)
    token = _observed.set(execution)
    try:
        with execution.phase(phase):
            yield execution
    finally:
        _observed.reset(token)


class BudgetExceeded(AgentError):
    pass


def failure_kind(exc):
    if isinstance(exc.__cause__, AgentError) and not isinstance(exc, AgentError):
        return failure_kind(exc.__cause__)
    message = str(exc)
    category = getattr(exc, 'category', None)
    if category in ('format', 'evidence-scope', 'review-format'):
        return category
    if category in ('semantic', 'verdict-conflict-risk', 'deterministic-validation'):
        return {'semantic': 'grounding-rejected', 'verdict-conflict-risk': 'no-progress',
                'deterministic-validation': 'validation'}[category]
    if isinstance(exc, BudgetExceeded):
        return 'budget'
    if 'checkpoint' in message:
        return 'checkpoint-integrity'
    if isinstance(exc, AgentError):
        if category in ('cli-missing', 'cli-authentication', 'cli-network'):
            return category
        if 'CLI 입력 한도' in message:
            return 'cli-input-limit'
        if '출력 토큰 한도' in message:
            return 'model-output-limit'
        if any(term in message.lower() for term in ('usage limit', 'usage-limit', 'rate limit', 'quota', '사용량')):
            return 'cli-usage-limit'
        return 'cli-timeout' if '시간이 초과' in message else 'cli-failure'
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return 'interrupted'
    if '근거 대조 실패' in message:
        return 'grounding-rejected'
    return 'validation'


class Execution:
    def __init__(self, cfg, agent, *, clock=time.monotonic, model=None):
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
        self.publication_contract = None
        self.publication_model = model
        self._pending_decisions = {}
        self._mutex = threading.RLock()
        self.operation = cfg.publication.get('operation_id')
        self.operation_limits = cfg.publication.get('budget', {})
        if (not isinstance(self.operation_limits, dict) or set(self.operation_limits) - {'max_calls', 'max_seconds'}
                or any(type(v) is not int or v < 0 for v in self.operation_limits.values())):
            raise ValueError('publication.budget accepts explicit nonnegative max_calls/max_seconds')
        if self.operation_limits and not self.operation:
            raise ValueError('publication.budget requires an operation_id across resumes')
        if self.operation is not None and (not isinstance(self.operation, str) or not self.operation.strip()):
            raise ValueError('publication.operation_id must be a nonempty string')
        self.report.update(operation_id=self.operation, operation_limits=self.operation_limits,
                           phases=[], owner_pid=os.getpid(), started_at=time.time())
        self.report['publication_plans'] = []
        if resume := _cli_resume.get():
            from .cli_agent import execution_profile
            self.report.update(resume_argv=resume, execution=execution_profile(cfg.agent),
                               source_commit=model.meta.get('source_commit') if model else None)
        if cfg.publication.get('operation_file'):
            self.report.update(publication=None, publication_attempt=None, publication_revision=None)

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
            tracked = {key for doc in self.report['documents'] for key in doc['units']}
            units['not-started'] += len(set(self.report.get('planned_units', ())) - tracked)
            self.report['counts'] = dict(completed=sum(units[s] for s in ('newly-generated', 'replayed', 'completed')),
                reused=sum(units[s] for s in ('manuscript-reused', 'checkpoint-reused')),
                revalidated=units['checkpoint-revalidated'], failed=units['failed'],
                running=units['running'], not_started=units['not-started'])
            prior = self.prior()
            self.report['cumulative'] = dict(calls=len(self.report['calls'])+sum(len(r.get('calls', [])) for r in prior),
                elapsed_seconds=self.report['seconds']+sum(r.get('seconds', 0) for r in prior),
                cli_seconds=sum(c.get('seconds', 0) for r in [*prior, self.report] for c in r.get('calls', [])))
            measured = [row['tokens'] for row in self.report['calls'] if row.get('tokens') is not None]
            self.report['tokens'] = dict(measured_attempts=len(measured),
                unmeasured_attempts=len(self.report['calls'])-len(measured),
                input=sum(row['input'] for row in measured) if measured else None,
                output=sum(row['output'] for row in measured) if measured else None)
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
        owns_contract = self.publication_contract is None and bool(self.cfg.publication.get('operation_file'))
        previous_role = None
        error = None
        try:
            with self.heartbeat():
                if owns_contract:
                    from .publication_operation import Contract
                    self.publication_contract = Contract(self, name)
                if self.publication_contract:
                    previous_role = self.publication_contract.role
                    self.publication_contract.enter_phase(name)
                if self.publication_contract and name == 'export_site':
                    self.publication_contract.final_gate()
                yield
                if self.publication_contract:
                    if owns_contract:
                        self.publication_contract.begin_output()
                    else:
                        self.publication_contract.verify()
            row['status'] = 'completed'
            row['seconds'] = self.clock()-self.started-row['started_seconds']
            self.report['current_phase'] = previous_phase
            self.persist()
        except BaseException as exc:
            error = exc
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            if owns_contract and self.publication_contract is not None:
                self.publication_contract.rollback()
            row['seconds'] = self.clock()-self.started-row['started_seconds']
            self.report['current_phase'] = previous_phase
            self.persist()
            raise
        finally:
            if self.publication_contract is not None:
                self.publication_contract.role = previous_role
            if owns_contract and self.publication_contract is not None:
                self.publication_contract.close(error)
                self.publication_contract = None

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
            for key, status in row['units'].items():
                if status == 'running':
                    row['units'][key] = 'failed'
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
            if status in ('completed', 'checkpoint-reused', 'checkpoint-revalidated', 'failed'):
                for value in self._pending_decisions.pop(key, []):
                    self.decision(key, {**value, 'stage': 'failed' if status == 'failed' else 'validated',
                                        'resolve_on_status': False, 'resolution_status': status})
            self.persist()

    def unit_if_pending(self, key, status):
        if self.current is not None and self.current['units'].get(key) == 'not-started':
            self.unit(key, status)

    def decision(self, key, value):
        """Append forecasts/resolutions without replacing statuses or provenance."""
        with self._mutex:
            self.report.setdefault('decisions', []).append(dict(unit=key,
                section=self.current['section'] if self.current else None,
                elapsed_seconds=self.clock()-self.started, **value))
            if value.get('resolve_on_status'):
                self._pending_decisions.setdefault(key, []).append(value)
            elif value.get('stage') in ('validated', 'failed'):
                self._pending_decisions.pop(key, None)
            self.persist()

    def units(self, states):
        """Persist a deterministic classification pass as one progress update."""
        if self.current is not None:
            with self._mutex:
                self.current['units'].update(states)
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
        resume = self.report.get('resume_argv')
        if resume:
            print(f'실행 장부: {self.path}')
        try:
            with self.phase(phase):
                yield
        finally:
            _observed.reset(token)
            if resume:
                tokens = self.report.get('tokens', {})
                counts = self.report.get('counts', {})
                print(f"실행 {self.report.get('seconds', 0):.3f}초, 호출 시도 {len(self.report['calls'])}회, "
                      f"단위 완료 {counts.get('completed', 0)}, 재사용 {counts.get('reused', 0)}, "
                      f"재검증 {counts.get('revalidated', 0)}, 실패 {counts.get('failed', 0)}, "
                      f"미시작 {counts.get('not_started', 0)}")
                measured = (f"{tokens['input']}/{tokens['output']}" if tokens.get('measured_attempts') else '미계측')
                print(f"계측된 토큰 (입력/출력): {measured}, "
                      f"미계측 시도 {tokens.get('unmeasured_attempts', 0)}회")
                if self.report['phases'] and self.report['phases'][-1]['status'] == 'failed':
                    kind = self.report['phases'][-1]['failure_kind']
                    print(f'중단 원인: {kind}. 기록을 보존한 뒤 같은 입력에서 재개할 명령 인자: '
                          + json.dumps(resume, ensure_ascii=False))

    def chat(self, system, user, **kwargs):
        return self._dispatch(self.agent.chat, system, user, **kwargs)

    def fresh_chat(self, system, user, **kwargs):
        transport = getattr(self.agent, 'fresh_chat', self.agent.chat)
        return self._dispatch(transport, system, user, **kwargs)

    def _dispatch(self, transport, system, user, **kwargs):
        from .execution_lock import lease
        if self.operation:
            import hashlib
            key = hashlib.sha256(self.operation.encode()).hexdigest()
            with lease(self.cfg, 'operation-'+key):
                return self._chat(transport, system, user, **kwargs)
        return self._chat(transport, system, user, **kwargs)

    def _chat(self, transport, system, user, **kwargs):
        if self.publication_contract:
            self.publication_contract.verify()
            self.publication_contract.verify_transport(transport)
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
        row['timeout_seconds'] = self.cfg.agent.timeout_sec
        try:
            with self.heartbeat():
                raw = transport(system, user, **kwargs)
            if self.publication_contract:
                self.publication_contract.verify()
                self.publication_contract.verify_transport(transport)
            self.check_time()
            row['status'] = 'completed'
            return raw
        except BaseException as exc:
            row.update(status='failed', failure_kind=failure_kind(exc), error=str(exc))
            raise
        finally:
            self.cfg.agent.timeout_sec = timeout
            row['seconds'] = self.clock()-now
            sender = getattr(transport, '__self__', None)
            if getattr(sender, 'cfg', None) is self.cfg.agent:
                if receipt := getattr(sender, 'last_receipt', None):
                    row['receipt'] = str(receipt)
                if record := getattr(sender, 'last_cli_attempt', None):
                    row.update(record)
            self.report['current_task'] = previous_task
            self.persist()
