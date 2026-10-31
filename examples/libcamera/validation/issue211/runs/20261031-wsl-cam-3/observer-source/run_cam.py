"""Run source-pinned unmodified official cam; fail closed on incomplete evidence."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from sdd.runtime_evidence import run_recorded, require_success, sha256, validate_dma, validate_frames

BASELINE = '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def validate_run(directory, *, camera, configuration, executable, libraries):
    record = require_success(directory)
    stdout = (directory / 'stdout').read_text()
    stderr = (directory / 'stderr').read_text()
    if f'Using camera {camera} as cam0' not in stdout:
        raise ValueError('Camera mismatch')
    configs = [line.split('configuring streams:', 1)[1].strip() for line in stderr.splitlines()
               if 'configuring streams:' in line]
    if configs != [configuration]:
        raise ValueError('Applied stream configuration mismatch')
    exit_record = json.loads((directory / 'inferior-exit.json').read_text())
    if exit_record != dict(exit_code=0, observation_failures=[]):
        raise ValueError('Inferior failed or observations are incomplete')
    loaded = json.loads((directory / 'loaded.json').read_text())
    if loaded['executable'] != str(executable.resolve()):
        raise ValueError('Different official executable was loaded')
    for path in [executable, *libraries]:
        if loaded['files'].get(str(path.resolve())) != sha256(path):
            raise ValueError('Loaded binary/library hash mismatch')
    allocations = rows(directory / 'allocations.jsonl')
    if not allocations or any(a['result'] < 0 or a['result'] == a['backing_fd']
                              or not a['providers'] or 'exp_name:\tudmabuf' not in a['fdinfo']
                              for a in allocations):
        raise ValueError('Official cam DMA provider/allocation not verified')
    result = validate_frames(rows(directory / 'events.jsonl'), expected_frames=3,
                             entry='callback-entry', processed='frame-processed',
                             complete_status=1, cancelled_status=2)
    metadata = rows(directory / 'buffers.jsonl')
    processed = {(e['request'], e['sequence']) for e in rows(directory / 'events.jsonl') if e['point'] == 'frame-processed'}
    if (len(metadata) != 3 or {(e['request'], e['sequence']) for e in metadata} != processed
            or any(e['buffer_status'] != 0 or e['status'] != 1 or e['buffer_sequence'] != e['sequence'] for e in metadata)):
        raise ValueError('Missing, duplicate or failed frame-buffer metadata')
    result['successful_buffer_sequences'] = [e['buffer_sequence'] for e in metadata]
    result.update(pid=loaded['pid'], allocations=len(allocations))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'posix' or 'microsoft' not in platform.release().lower():
        raise ValueError('This issue requires WSL; other Linux runs are preliminary only')
    source, build, out = args.source.resolve(), args.build.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    git = ['git', '-c', 'safe.directory=' + str(source)]
    commit = subprocess.check_output([*git, 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if commit != BASELINE or subprocess.check_output([*git, 'status', '--porcelain', '--untracked-files=no'], cwd=source):
        raise ValueError('Baseline SHA or clean source contract failed')
    executable = build / 'src/apps/cam/cam'
    libraries = [build / 'src/libcamera/libcamera.so', build / 'src/libcamera/base/libcamera-base.so']
    environment = dict(LIBCAMERA_PIPELINES_MATCH_LIST='virtual', LIBCAMERA_LOG_LEVELS='*:DEBUG',
                       LD_LIBRARY_PATH=str(args.tools.resolve() / 'usr/lib/x86_64-linux-gnu'))
    if os.environ.get('LD_PRELOAD') or os.environ.get('LD_AUDIT'):
        raise ValueError('Loader injection is not allowed')
    record = dict(schema=1, source_commit=commit, source_tracked_clean=True, kernel=platform.release(), results=[],
                  uid=os.getuid(), gid=os.getgid(),
                  observer_inputs={str(p): sha256(p) for p in [Path(__file__), Path(__file__).with_name('observe_cam.gdb.py')]},
                  inherited_runtime_environment={key: value for key, value in os.environ.items()
                                                 if key.startswith(('LD_', 'LIBCAMERA_'))},
                  binaries={str(p): sha256(p) for p in [executable, *libraries, args.probe]},
                  human_review='pending', physical_dma='not-validated', physical_camera='not-run',
                  production_application='not-run', internal_hal='not-run', status='incomplete')
    try:
        run_recorded(out / 'dma-probe', [str(args.probe.resolve())], timeout=15)
        require_success(out / 'dma-probe')
        validate_dma(rows(out / 'dma-probe/stdout'))
        for index in range(3):
            directory = out / f'cam-{index + 1}'
            env = dict(environment, ISSUE211_OUT=str(directory), ISSUE211_SOURCE=str(source))
            argv = [str(args.tools.resolve() / 'usr/bin/gdb'),
                    '--data-directory=' + str(args.tools.resolve() / 'usr/share/gdb'),
                    '--batch', '--nx', '--nh', '-q', '-iex', 'set auto-load off',
                    '-ex', 'set debuginfod enabled off', '-ex', 'set pagination off',
                    '-ex', 'set startup-with-shell off', '-x', str(Path(__file__).with_name('observe_cam.gdb.py').resolve()),
                    '--args', str(executable), '--camera', 'Virtual2', '--capture=3',
                    '--stream', 'role=video,width=400,height=300,pixelformat=NV12']
            run_recorded(directory, argv, timeout=45, environment=env)
            result = validate_run(directory, camera='Virtual2', configuration='(0) 400x300-NV12/SMPTE170M',
                                  executable=executable, libraries=libraries)
            record['results'].append(result)
        if len({r['pid'] for r in record['results']}) != 3:
            raise ValueError('Not three independent official cam processes')
        record['status'] = 'observed-wsl-virtual-only'
    except (ValueError, OSError) as exc:
        record['failure'] = str(exc)
        raise
    finally:
        record['artifacts'] = {str(p.relative_to(out)): sha256(p) for p in out.rglob('*') if p.is_file()}
        (out / 'observation.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
