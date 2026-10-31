"""OS-owned execution leases: observing a live task never starts a duplicate."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
from pathlib import Path
import time

from .state_io import save

_active = ContextVar('sdd_execution_lease', default=None)


class AlreadyRunning(RuntimeError):
    pass


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Unknown due to access: do not duplicate.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def lease(cfg, purpose):
    import json
    path = cfg.build_dir/'execution-locks'/f'{purpose}.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    status = path.with_suffix('.json')
    with path.open('a+b') as stream:
        stream.seek(0)
        if not os.fstat(stream.fileno()).st_size:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AlreadyRunning(f'{purpose} is still running; observe {status}; do not restart') from exc
        token = None
        try:
            previous = json.loads(status.read_bytes()) if status.exists() else {}
            if previous.get('status') == 'running' and alive(previous.get('worker_pid')):
                raise AlreadyRunning(f'{purpose} CLI worker is still alive; observe {status}; do not restart')
            row = dict(purpose=purpose, owner_pid=os.getpid(), worker_pid=None,
                       status='running', started_at=time.time())
            save(status, row)
            token = _active.set([*(_active.get() or []), (status, row)])
            try:
                yield
                row['status'] = 'completed'
            except BaseException as exc:
                row.update(status='failed', error=str(exc))
                raise
            finally:
                row['finished_at'] = time.time()
                save(status, row)
        finally:
            if token is not None:
                _active.reset(token)
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def worker(pid):
    for path, row in _active.get() or []:
        row['worker_pid'] = pid
        save(path, row)


def locked(purpose):
    def decorate(function):
        @wraps(function)
        def wrapped(first, *args, **kwargs):
            cfg = first.cfg if hasattr(first, 'cfg') else first
            with lease(cfg, purpose):
                return function(first, *args, **kwargs)
        return wrapped
    return decorate
