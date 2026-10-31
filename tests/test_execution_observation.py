import json
import os
import threading
import time

import pytest

from sdd.execution_lock import AlreadyRunning, alive, lease, worker
from sdd.generation_run import BudgetExceeded, Execution


def test_live_operation_is_observed_not_restarted_and_lease_is_released(tmp_cfg):
    assert alive(os.getpid())
    with lease(tmp_cfg, 'same'):
        with pytest.raises(AlreadyRunning, match='still running'):
            with lease(tmp_cfg, 'same'):
                pytest.fail('duplicate execution')
    with lease(tmp_cfg, 'same'):
        pass


def test_orphan_live_worker_blocks_duplicate_after_owner_exits(tmp_cfg):
    from sdd.state_io import save
    path = tmp_cfg.build_dir/'execution-locks/same.json'
    save(path, dict(status='running', worker_pid=os.getpid()))
    with pytest.raises(AlreadyRunning, match='worker is still alive'):
        with lease(tmp_cfg, 'same'):
            pytest.fail('duplicate worker')


def test_heartbeat_updates_a_silent_stage_and_records_failure(tmp_cfg):
    execution = Execution(tmp_cfg, object())
    with pytest.raises(KeyboardInterrupt):
        with execution.heartbeat(interval=.02):
            first = json.loads(execution.path.read_bytes())
            deadline = time.monotonic() + 2
            while True:
                second = json.loads(execution.path.read_bytes())
                if second['updated_at'] > first['updated_at'] or time.monotonic() >= deadline:
                    break
                time.sleep(.01)
            assert second['updated_at'] > first['updated_at']
            assert second['seconds'] > first['seconds']
            raise KeyboardInterrupt()
    assert execution.path.exists()


def test_operation_budget_counts_failed_calls_across_resume(tmp_cfg):
    tmp_cfg.raw['publication'] = dict(operation_id='one-task', budget=dict(max_calls=1))
    class Agent:
        def chat(self, *args, **kwargs):
            raise RuntimeError('interrupted worker')
    first = Execution(tmp_cfg, Agent())
    with pytest.raises(RuntimeError):
        first.chat('system', 'user')
    second = Execution(tmp_cfg, Agent())
    with pytest.raises(BudgetExceeded, match='operation call'):
        second.chat('system', 'user')
    second.persist()
    assert second.report['cumulative']['calls'] == 1
    assert not second.report['calls']
    assert first.report['calls'][0]['status'] == 'failed'


def test_only_explicit_operation_budget_is_used(tmp_cfg):
    execution = Execution(tmp_cfg, object())
    assert execution.operation_limits == {}
    tmp_cfg.raw['publication'] = dict(budget=dict(max_calls=1))
    with pytest.raises(ValueError, match='operation_id'):
        Execution(tmp_cfg, object())
