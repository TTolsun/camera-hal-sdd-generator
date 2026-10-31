"""Read-only runtime tests and dedicated negative probes, before kernel approval."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'src'))
from sdd.runtime_evidence import run_recorded, require_success

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
work, out = args.work.resolve(), args.out.resolve()
probe = work / 'dmabuf-probe-2'
run_recorded(out / 'compile-probe', ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-g', '-O0',
                                  str(root / 'examples/libcamera/runtime/dmabuf_probe.c'), '-o', str(probe)], timeout=30)
require_success(out / 'compile-probe')
for name, provider in [('provider-absent', '/dev/issue211-deliberately-absent'), ('ioctl-unsupported', '/dev/null'),
                       ('current-udmabuf', '/dev/udmabuf')]:
    result = run_recorded(out / name, [str(probe), provider], timeout=15)
    print(name, json.dumps(result), flush=True)
    if name != 'current-udmabuf' and (result['exit_code'] != 1 or result['timed_out']):
        raise RuntimeError('Dedicated negative probe did not fail as expected')
# Exercise the debugger even before DMA exists. This is an expected failed cam,
# not a capture success. Keep the actual inferior exit and raw debugger output.
directory = out / 'official-cam-debugger-before'
env = dict(ISSUE211_OUT=str(directory), ISSUE211_SOURCE=str(work / 'source'),
           LIBCAMERA_PIPELINES_MATCH_LIST='virtual', LIBCAMERA_LOG_LEVELS='*:DEBUG',
           LD_LIBRARY_PATH=str(work / 'tools/usr/lib/x86_64-linux-gnu'))
argv = [str(work / 'tools/usr/bin/gdb'), '--data-directory=' + str(work / 'tools/usr/share/gdb'),
        '--batch', '--nx', '--nh', '-q', '-iex', 'set auto-load off',
        '-ex', 'set debuginfod enabled off', '-ex', 'set pagination off', '-ex', 'set startup-with-shell off',
        '-x', str(root / 'examples/libcamera/runtime/observe_cam.gdb.py'), '--args',
        str(work / 'build/src/apps/cam/cam'), '--camera', 'Virtual2', '--capture=3',
        '--stream', 'role=video,width=400,height=300,pixelformat=NV12']
print('debugger', json.dumps(run_recorded(directory, argv, timeout=45, environment=env)), flush=True)
