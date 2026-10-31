"""Run unmodified public libcamera's virtual pipeline; no physical/DMA claim.

Run on Linux with a source-pinned existing Meson build. The application supplies
CPU memfd buffers and unsignalled eventfd test fences. DMA sync failures are
retained, not suppressed or interpreted as successful DMA validation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import subprocess


if not __debug__:
    raise RuntimeError("Run without Python optimization: validation requires assertions.")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(events):
    assert [e['index'] for e in events] == list(range(len(events)))
    assert events[-1]['event'] == 'probe-pass' and events[-1]['request_callbacks'] == 24
    main = events[0]['tid']
    entries = [e for e in events if e['event'] == 'callback-enter']
    exits = [e for e in events if e['event'] == 'callback-return']
    assert len(entries) == len(exits) == 24
    records = []
    for connection in ('auto', 'direct', 'queued'):
        for phase, cookies, status in [('normal', range(100, 104), 1), ('stop', range(200, 204), 2)]:
            selected = [e for e in entries if e['connection'] == connection and e['cookie'] in cookies]
            assert [e['cookie'] for e in selected] == list(cookies)
            assert [e['sequence'] for e in selected] == list(range(4))
            assert all(e['status'] == status and e['receiver_tid'] == main for e in selected)
            assert all(e['affinity_match'] == (connection != 'direct') for e in selected)
            assert all((e['tid'] == main) == (connection != 'direct') for e in selected)
            assert all(e['inside_stop'] == (phase == 'stop' and connection == 'direct') for e in selected)
            for entry in selected:
                match = [e for e in exits if (e['connection'], e['cookie']) == (connection, entry['cookie'])]
                assert len(match) == 1 and match[0]['index'] > entry['index']
                assert (match[0]['tid'], match[0]['status']) == (entry['tid'], entry['status'])
                if phase == 'stop':
                    stop = next(e for e in events if e['event'] == 'stop-enter' and e['phase'] == 1)
                    returned = next(e for e in events if e['event'] == 'stop-return' and e['phase'] == 1)
                    assert stop['index'] < entry['index'] < match[0]['index'] < returned['index'] if connection == 'direct' else returned['index'] < entry['index'] < match[0]['index']
            records.append(dict(connection=connection, phase=phase, callbacks=len(selected),
                                status='RequestComplete' if status == 1 else 'RequestCancelled',
                                callback_tids=sorted({e['tid'] for e in selected}), receiver_tid=main,
                                receiver_affinity_matches=connection != 'direct',
                                during_stop_call=phase == 'stop' and connection == 'direct'))
    buffers = [e for e in events if e['event'] == 'buffer']
    assert len(buffers) == 8 and [e['cookie'] for e in buffers] == list(range(100, 104)) + list(range(200, 204))
    assert [e['status'] for e in buffers] == [0] * 4 + [2] * 4  # FrameSuccess/FrameCancelled, not DMA proof.
    return dict(callbacks=24, normal_requests=4, stop_cancelled_requests=4, connections=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    assert 1 <= args.runs <= 10
    source, build, out = args.source.resolve(), args.build.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    assert commit == args.expected_commit and len(commit) == 40
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source, text=True).strip()
    probe = Path(__file__).with_name('callback_probe.cpp').resolve()
    binary = out/'callback-probe'

    def execute(name, command, *, env=None, timeout=120):
        run = subprocess.run(command, capture_output=True, env=env, timeout=timeout)
        (out/(name+'.stdout')).write_bytes(run.stdout)
        (out/(name+'.stderr')).write_bytes(run.stderr)
        assert run.returncode == 0, f'{name} exited {run.returncode}; raw output retained'
        return run

    execute('build', ['ninja', '-C', str(build)])
    compile_args = ['g++', '-std=c++20', '-DLIBCAMERA_BASE_PRIVATE', '-g', '-O0', '-pthread',
                    '-I'+str(source/'include'), '-I'+str(build/'include'), str(probe),
                    '-L'+str(build/'src/libcamera'), '-L'+str(build/'src/libcamera/base'),
                    '-Wl,-rpath,'+str(build/'src/libcamera')+':'+str(build/'src/libcamera/base'),
                    '-lcamera', '-lcamera-base', '-o', str(binary)]
    execute('compile', compile_args)
    execute('linked-libraries', ['ldd', str(binary)])
    env = dict(os.environ, LIBCAMERA_PIPELINES_MATCH_LIST='virtual')
    results = []
    for index in range(args.runs):
        name = f'run-{index+1}'
        run = execute(name, [str(binary)], env=env, timeout=25)
        rows = [json.loads(line) for line in run.stdout.decode().splitlines()]
        result = validate(rows)
        errors = [line for line in run.stderr.decode().splitlines() if 'ERROR' in line]
        assert all('Could not open any dma-buf provider' in line or 'Unable to sync dma fd' in line for line in errors), errors
        assert sum('Could not open any dma-buf provider' in line for line in errors) == 2
        assert sum('Unable to sync dma fd' in line for line in errors) == 8
        result.update(run=index+1, raw_stdout_sha256=sha(out/(name+'.stdout')),
                      raw_stderr_sha256=sha(out/(name+'.stderr')), retained_error_lines=errors)
        results.append(result)
    record = dict(schema=1, source_commit=commit, source_tree_clean=True,
                  probe_sha256=sha(probe), binary_sha256=sha(binary), compile_command=compile_args,
                  libraries={str(p.resolve()): sha(p.resolve()) for p in [build/'src/libcamera/libcamera.so', build/'src/libcamera/base/libcamera-base.so']},
                  kernel=platform.release(), pipeline='virtual', camera='Virtual2',
                  format='NV12', size=[400, 300], buffer_kind='application memfd, CPU-only, not DMA-BUF',
                  stop_fence='unsignalled eventfd test input, not a kernel sync_file',
                  callback_return_marker='Near-return marker before the counter increment and local destruction; does not trace the actual C++ return.',
                  run_count=args.runs, total_callbacks=sum(r['callbacks'] for r in results), results=results,
                  validation_scope='Actual callback dispatch/entry/return markers/status/order/thread in this controlled public virtual probe only.',
                  dma_validation='not validated; provider/sync errors retained', physical_camera_validation='not-run',
                  production_application_validation='not-run', internal_hal_validation='not-run', human_review='pending')
    (out/'observation.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status='observed-public-virtual-callbacks-only', runs=args.runs, callbacks=record['total_callbacks'], dma='unvalidated-errors-retained')))


if __name__ == '__main__':
    main()
