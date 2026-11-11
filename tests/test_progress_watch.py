import json
import os

from sdd.progress_watch import watch


def test_stall_alert_is_durable_and_fires_once_until_progress_resumes(tmp_path):
    activity = tmp_path/'activity.jsonl'
    stop = tmp_path/'finished'
    alerts = tmp_path/'alerts.jsonl'
    notifications = []
    now = 1000

    def touch():
        activity.write_text(str(now), encoding='utf-8')
        os.utime(activity, (now, now))

    def sleep(seconds):
        nonlocal now
        now += seconds
        if now == 1009:
            touch()
        if now == 1017:
            stop.touch()

    touch()
    watch(activity, stop, alerts, idle_seconds=5, interval=1, max_seconds=20,
          clock=lambda: now, monotonic=lambda: now, sleep=sleep, notify=notifications.append)
    events = [json.loads(line) for line in alerts.read_text(encoding='utf-8').splitlines()]
    assert [(event['status'], event['at']) for event in events] == [
        ('stalled', 1005), ('resumed', 1009), ('stalled', 1014)]
    assert len(notifications) == 2


def test_completed_run_does_not_alert(tmp_path):
    stop = tmp_path/'finished'
    stop.touch()
    alerts = tmp_path/'alerts.jsonl'
    watch(tmp_path/'missing', stop, alerts, idle_seconds=1, interval=1, max_seconds=1)
    assert not alerts.exists()
