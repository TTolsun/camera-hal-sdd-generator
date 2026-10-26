"""Atomic JSON state persistence without workflow dependencies."""
import json
import tempfile
import time
from pathlib import Path


def save(path, data, *, indent=2, sort_keys=False, newline=None):
    """Replace one complete JSON file; callers own read/modify/write locking."""
    text = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Exclusive creation isolates overlapping saves and stale temporary files.
        # Keep the file beside its destination for a same-filesystem replacement.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline=newline,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
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
                if getattr(exc, "winerror", None) not in (5, 32, 33) or index == len(delays) - 1:
                    raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
