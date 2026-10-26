"""Atomic JSON state persistence without workflow dependencies."""
import json
import time

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Windows readers/scanners can briefly deny an otherwise valid atomic
    # replacement. Retry the same prepared file; never delete the old state.
    delays = (0, .01, .025, .05, .1, .2, .4)
    for index, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or index == len(delays) - 1:
                raise
