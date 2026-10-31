"""Supplemental real syscalls and cooperative timeout cleanup; not callbacks."""
import argparse
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'src'))
from sdd.runtime_evidence import run_recorded, require_success, sha256

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out, work = args.out.resolve(), args.work.resolve()
out.mkdir(parents=True, exist_ok=False)
environment = dict(LD_LIBRARY_PATH=str(work / 'tools/usr/lib/x86_64-linux-gnu'),
                   LIBCAMERA_PIPELINES_MATCH_LIST='virtual', LIBCAMERA_LOG_LEVELS='*:DEBUG')
record = run_recorded(out / 'probe-timeout', [str(work / 'dmabuf-probe-2'), '/dev/udmabuf', '--pause-after-start'], timeout=.5)
events = [json.loads(line) for line in (out / 'probe-timeout/stdout').read_text().splitlines()]
if not record['timed_out'] or record['exit_code'] != 1 or not record['group_absent']:
    raise RuntimeError('Timeout/cleanup not observed')
if [e['event'] for e in events] != ['provider-open', 'allocate', 'mmap', 'sync-start', 'sync-end',
                                    'munmap', 'close-dmabuf', 'close-backing', 'close-provider']:
    raise RuntimeError('Timed-out probe did not release all resources')
if any(e['result'] < 0 or e['errno'] for e in events):
    raise RuntimeError('Timeout cleanup operation failed')
command = [str(work / 'tools/usr/bin/strace'), '-f', '-yy', '-s', '256',
           '-e', 'trace=openat,ioctl,mmap,munmap,close,memfd_create,fcntl', '-o', str(out / 'official-cam.strace'),
           str(work / 'build/src/apps/cam/cam'), '--camera', 'Virtual2', '--capture=3',
           '--stream', 'role=video,width=400,height=300,pixelformat=NV12']
run_recorded(out / 'strace-cam', command, timeout=20, environment=environment)
require_success(out / 'strace-cam')
trace = (out / 'official-cam.strace').read_text()
for token in ('/dev/udmabuf', 'UDMABUF_CREATE', 'DMA_BUF_IOCTL_SYNC', 'munmap(', 'close(', 'exited with 0'):
    if token not in trace:
        raise RuntimeError('Missing syscall evidence: ' + token)
summary = dict(schema=1, status='supplemental-real-syscalls-and-timeout-cleanup', uid=os.getuid(),
               callback_observation=False, timeout_cleanup=True,
               artifacts={str(p.relative_to(out)): sha256(p) for p in out.rglob('*') if p.is_file()})
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
