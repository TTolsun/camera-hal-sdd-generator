import copy
import json
import sys

import pytest

from sdd.runtime_evidence import require_success, run_recorded, validate_dma, validate_frames


def frames():
    return [dict(point=point, request=f'0x{sequence + 1}', sequence=sequence, status=1, tid=tid)
            for sequence in range(3) for point, tid in [('entry', 31), ('processed', 30)]]


def check(events):
    return validate_frames(events, expected_frames=3, entry='entry', processed='processed',
                           complete_status=1, cancelled_status=2)


def test_frames_join_identity_and_separate_cancellation():
    events = frames() + [dict(point='entry', request='0x4', sequence=3, status=2, tid=31)]
    assert check(events) == dict(completed_frames=3, cancelled_callbacks=1, observed_tids=[30, 31])


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'pending', 'thread', 'sequence', 'order'])
def test_incomplete_observations_fail(change):
    events = frames()
    if change == 'missing':
        events.pop()
    elif change == 'duplicate':
        events.append(copy.copy(events[0]))
    elif change == 'pending':
        events[0]['status'] = 0
    elif change == 'thread':
        events[0].pop('tid')
    elif change == 'sequence':
        events[-1]['sequence'] = 0
    else:
        events[0], events[1] = events[1], events[0]
    with pytest.raises(ValueError):
        check(events)


def test_raw_failure_timeout_and_no_overwrite(tmp_path):
    out = tmp_path / 'run'
    record = run_recorded(out, [sys.executable, '-u', '-c',
                          'import time; print("before timeout"); time.sleep(10)'], timeout=.2)
    assert record['timed_out'] and b'before timeout' in (out / 'stdout').read_bytes()
    with pytest.raises(ValueError):
        require_success(out)
    with pytest.raises(FileExistsError):
        run_recorded(out, [sys.executable, '-c', 'pass'], timeout=1)


@pytest.mark.parametrize('body', ['import sys; sys.exit(2)', 'import sys; print("ERROR sync", file=sys.stderr)'])
def test_exit_zero_does_not_hide_dma_errors(tmp_path, body):
    run_recorded(tmp_path / 'run', [sys.executable, '-c', body], timeout=5)
    with pytest.raises(ValueError):
        require_success(tmp_path / 'run')


def test_raw_hash_and_missing_record_fail(tmp_path):
    out = tmp_path / 'run'
    run_recorded(out, [sys.executable, '-c', 'print("ok")'], timeout=5)
    require_success(out)
    (out / 'stdout').write_bytes(b'changed')
    with pytest.raises(ValueError):
        require_success(out)


def dma_events():
    names = ['provider-open', 'allocate', 'mmap', 'sync-start', 'cpu-access', 'sync-end',
             'munmap', 'close-dmabuf', 'close-backing', 'close-provider']
    events = [dict(event=name, result=0, errno=0) for name in names]
    events[1].update(result=5, dmabuf_fd=5, backing_fd=4)
    events[4].update(bytes=4096, checksum=522240)
    events[3]['flags'], events[5]['flags'] = 3, 7
    return events


def test_dma_real_lifecycle_contract():
    validate_dma(dma_events())


def test_duplicate_cancel_callback_is_not_silently_counted():
    cancellation = dict(point='entry', request='0x4', sequence=3, status=2, tid=31)
    with pytest.raises(ValueError):
        check(frames() + [cancellation, cancellation])


def test_dma_retries_require_current_phase_and_rw_flags():
    events = dma_events()
    retry = dict(event='sync-start', result=-1, errno=4, flags=3, retry=True)
    events.insert(3, retry)
    validate_dma(events)
    events[3]['flags'] = 1
    with pytest.raises(ValueError):
        validate_dma(events)
    events = dma_events()
    events.insert(0, dict(retry, flags=3))
    with pytest.raises(ValueError):
        validate_dma(events)


@pytest.mark.parametrize('change', ['allocation', 'sync', 'missing', 'memfd', 'direction'])
def test_dma_failures_are_never_cpu_memfd_success(change):
    events = dma_events()
    if change == 'allocation':
        events[1].update(result=-1, errno=19)
    elif change == 'sync':
        events[3].update(result=-1, errno=25)
    elif change == 'missing':
        events.pop(4)
    elif change == 'memfd':
        events[1]['dmabuf_fd'] = 4
    else:
        events[3]['flags'] = 1
    with pytest.raises(ValueError):
        validate_dma(events)
