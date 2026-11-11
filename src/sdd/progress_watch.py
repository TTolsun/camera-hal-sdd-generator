"""Watch one run from a process independent of the producer."""
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID


def desktop_alert(message):
    """Show a local notification while the watcher continues polling."""
    import ctypes
    from threading import Thread

    show = ctypes.windll.user32.MessageBoxW
    show.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    Thread(target=show,
           args=(None, message, 'SDD 진행 기록', 0x00040030), daemon=True).start()


def watch(activity, stop_file, alerts, *, idle_seconds, interval, max_seconds,
          clock=time.time, monotonic=time.monotonic, sleep=time.sleep, notify=None):
    if min(idle_seconds, interval, max_seconds) <= 0:
        raise ValueError('Watch intervals and duration must be positive')
    activity, stop_file, alerts = (Path(path).resolve() for path in (activity, stop_file, alerts))
    if len({activity, stop_file, alerts}) != 3:
        raise ValueError('The activity, stop marker and alert log must be different files')
    deadline = monotonic() + max_seconds
    last_seen = clock()
    previous = None
    stalled = False
    alerts.parent.mkdir(parents=True, exist_ok=True)
    while not stop_file.exists() and monotonic() < deadline:
        now = clock()
        try:
            stat = activity.stat()
        except FileNotFoundError:
            signature = None
        else:
            signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        if signature != previous:
            last_seen = min(now, stat.st_mtime) if signature is not None else now
            previous = signature
        idle = max(0, now - last_seen)
        is_stalled = idle >= idle_seconds
        if is_stalled != stalled:
            status = 'stalled' if is_stalled else 'resumed'
            message = (f'{idle:.0f}초 동안 진행 기록이 갱신되지 않았습니다. ({activity.name})'
                       if is_stalled else f'진행 기록 갱신을 확인했습니다. ({activity.name})')
            event = dict(status=status, at=now, activity=activity.name, last_activity_at=last_seen,
                         idle_seconds=round(idle, 1), activity_exists=signature is not None)
            with alerts.open('a', encoding='utf-8') as log:
                log.write(json.dumps(event, ensure_ascii=False) + '\n')
                log.flush()
                os.fsync(log.fileno())
            print(message, file=sys.stderr, flush=True)
            if is_stalled and notify is not None:
                notify(message)
            stalled = is_stalled
        sleep(min(interval, max(0, deadline - monotonic())))


def command(args):
    if args.desktop and os.name != 'nt':
        raise ValueError('--desktop requires an interactive Windows session')
    activity = args.activity if args.activity else codex_activity(args.codex_thread)
    watch(activity, args.stop_file, args.alerts, idle_seconds=args.idle_seconds,
          interval=args.interval, max_seconds=args.max_seconds,
          notify=desktop_alert if args.desktop else None)
    return 0


def codex_activity(thread):
    thread_id = str(UUID(thread))
    root = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'sessions'
    matches = list(root.glob(f'*/*/*/rollout-*-{thread_id}.jsonl'))
    if len(matches) != 1:
        raise ValueError('Could not identify one active Codex session log; pass --activity explicitly')
    return matches[0]
