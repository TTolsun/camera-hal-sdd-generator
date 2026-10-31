"""Immutable command records and strict runtime observations (no approval grant)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run_recorded(out, argv, *, timeout, cwd=None, environment=None):
    """Keep raw bytes even on timeout; refuse to overwrite earlier evidence.

    Only explicitly supplied environment overrides are published. On POSIX a
    private process group includes descendants; remaining group members are
    terminated even if the parent exits normally. Windows timeout uses taskkill.
    """
    if timeout <= 0 or not argv:
        raise ValueError('A command and positive timeout are required')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    record = dict(schema=1, argv=list(map(str, argv)), cwd=str(Path(cwd or '.').resolve()),
                  environment=environment or {}, timeout_seconds=timeout,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  timed_out=False, exit_code=None, cleanup='not-started')
    try:
        with (out / 'stdout').open('xb') as stdout, (out / 'stderr').open('xb') as stderr:
            proc = subprocess.Popen(argv, cwd=cwd, env={**os.environ, **(environment or {})},
                                    stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    start_new_session=os.name != 'nt',
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            record['pid'] = proc.pid
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                if os.name != 'nt':
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if os.name == 'nt':
                    if proc.poll() is None:
                        cleanup = subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                                 capture_output=True, timeout=10)
                        (out / 'cleanup.stdout').write_bytes(cleanup.stdout)
                        (out / 'cleanup.stderr').write_bytes(cleanup.stderr)
                        proc.kill()
                    proc.wait(timeout=10)
                    record['cleanup'] = 'parent-reaped-windows'
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                        record['cleanup'] = 'remaining-process-group-killed'
                    except ProcessLookupError:
                        record['cleanup'] = 'process-group-empty'
                    proc.wait(timeout=10)
                    try:
                        os.killpg(proc.pid, 0)
                        record['group_absent'] = False
                    except ProcessLookupError:
                        record['group_absent'] = True
                record['exit_code'] = proc.returncode
    except OSError as exc:
        record['launch_error'] = str(exc)
    finally:
        record['elapsed_seconds'] = time.monotonic() - start
        record['files'] = {p.name: sha256(p) for p in out.iterdir() if p.is_file()}
        (out / 'record.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def require_success(directory):
    """Verify archived bytes before consulting an execution result."""
    directory = Path(directory)
    record = json.loads((directory / 'record.json').read_text(encoding='utf-8'))
    if not {'stdout', 'stderr'} <= record['files'].keys():
        raise ValueError('Missing raw output')
    for name, digest in record['files'].items():
        if Path(name).name != name or sha256(directory / name) != digest:
            raise ValueError('Changed runtime evidence')
    if (record.get('launch_error') or record['timed_out'] or record['exit_code'] != 0
            or record.get('group_absent') is False):
        raise ValueError('Runtime command failed or cleanup is incomplete')
    if b'ERROR' in (directory / 'stderr').read_bytes():
        raise ValueError('Unexpected runtime ERROR')
    return record


def validate_frames(events, *, expected_frames, entry, processed, complete_status, cancelled_status):
    """Join two real observation points by (request address, sequence).

    Cancellation entries are separate, never normal frames. This validator does
    not infer callback returns, thread affinity, or physical device correctness.
    """
    entries, handled, cancelled, seen_entries = {}, {}, [], set()
    for index, event in enumerate(events):
        if event.get('point') not in (entry, processed):
            raise ValueError('Unknown observation point')
        if not isinstance(event.get('tid'), int) or event['tid'] <= 0:
            raise ValueError('Missing OS thread identity')
        if not event.get('request') or not isinstance(event.get('sequence'), int):
            raise ValueError('Missing request identity or sequence')
        key = (event['request'], event['sequence'])
        if event['point'] == entry:
            if key in seen_entries:
                raise ValueError('Duplicate callback entry')
            seen_entries.add(key)
        if event.get('status') == cancelled_status and event['point'] == entry:
            cancelled.append(event)
            continue
        if event.get('status') != complete_status:
            raise ValueError('Frame is not complete')
        target = entries if event['point'] == entry else handled
        if key in target:
            raise ValueError('Duplicate callback observation')
        target[key] = index
    if len(entries) != expected_frames or entries.keys() != handled.keys():
        raise ValueError('Missing or extra completed frames')
    if len({key[1] for key in entries}) != expected_frames:
        raise ValueError('Repeated frame sequence')
    if any(entries[key] >= handled[key] for key in entries):
        raise ValueError('Processing precedes callback entry')
    return dict(completed_frames=len(entries), cancelled_callbacks=len(cancelled),
                observed_tids=sorted({e['tid'] for e in events}))


def validate_dma(events):
    """Require successful allocation, map, bracketed CPU access and cleanup."""
    expected = ['provider-open', 'allocate', 'mmap', 'sync-start', 'cpu-access',
                'sync-end', 'munmap', 'close-dmabuf', 'close-backing', 'close-provider']
    if [e.get('event') for e in events if not e.get('retry')] != expected:
        raise ValueError('Missing or out-of-order DMA lifecycle')
    for event in events:
        if event.get('retry'):
            if event.get('event') not in ('sync-start', 'sync-end') or event.get('errno') not in (4, 11):
                raise ValueError('Invalid DMA retry')
        elif event.get('errno') != 0 or event.get('result', -1) < 0:
            raise ValueError('DMA operation failed')
    start = next(e for e in events if e['event'] == 'sync-start' and not e.get('retry'))
    end = next(e for e in events if e['event'] == 'sync-end' and not e.get('retry'))
    if start.get('flags') != 3 or end.get('flags') != 7:
        raise ValueError('Read/write CPU access requires matching RW START/END')
    allocate = next(e for e in events if e['event'] == 'allocate')
    if allocate.get('dmabuf_fd') == allocate.get('backing_fd') or allocate.get('dmabuf_fd', -1) < 0:
        raise ValueError('Backing fd is not the exported DMA-BUF')
