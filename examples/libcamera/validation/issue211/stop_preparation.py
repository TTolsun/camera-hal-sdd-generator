"""Stop only this issue's unfinished kernel preparation process trees."""
import os
from pathlib import Path
import signal

processes = {}
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        args = (entry / 'cmdline').read_bytes().split(b'\0')
        parent = int((entry / 'status').read_text().split('PPid:')[1].splitlines()[0])
        processes[int(entry.name)] = (parent, args)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
targets = {pid for pid, (_, args) in processes.items()
           if any(arg.endswith(b'/issue211/prepare_kernel.sh') for arg in args)}
while True:
    descendants = {pid for pid, (parent, _) in processes.items() if parent in targets}
    combined = targets | descendants
    if combined == targets:
        break
    targets = combined
for pid in sorted(targets, reverse=True):
    print('terminate-task-preparation', pid, flush=True)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
