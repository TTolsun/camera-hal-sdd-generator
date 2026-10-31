"""Negative contract tests, never actual kernel/camera evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('official_cam', Path(__file__).resolve().parents[1] /
                                            'examples/libcamera/runtime/run_cam.py')
cam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cam)


def test_meson_build_must_belong_to_the_pinned_checkout(tmp_path):
    source, build = tmp_path / 'source', tmp_path / 'build'
    (build / 'meson-info').mkdir(parents=True)
    info = build / 'meson-info/meson-info.json'
    info.write_text(json.dumps(dict(directories=dict(source=str(source), build=str(build)))))
    cam.verify_build_source(source, build)
    info.write_text(json.dumps(dict(directories=dict(source=str(tmp_path / 'other-commit'), build=str(build)))))
    with pytest.raises(ValueError, match='build/source directory mismatch'):
        cam.verify_build_source(source, build)


@pytest.mark.parametrize('configuration', ['(0) 640x480-NV12/SMPTE170M', '(0) 400x300-RGB888/sRGB', ''])
def test_configuration_mismatch_never_passes(tmp_path, monkeypatch, configuration):
    monkeypatch.setattr(cam, 'require_success', lambda _: {})
    (tmp_path / 'stdout').write_text('Using camera Virtual2 as cam0\n')
    (tmp_path / 'stderr').write_text('INFO configuring streams: ' + configuration + '\n')
    with pytest.raises(ValueError, match='configuration mismatch'):
        cam.validate_run(tmp_path, camera='Virtual2', configuration='(0) 400x300-NV12/SMPTE170M',
                         executable=tmp_path / 'cam', libraries=[])


def test_debugger_exit_zero_is_not_inferior_success(tmp_path, monkeypatch):
    monkeypatch.setattr(cam, 'require_success', lambda _: {})
    (tmp_path / 'stdout').write_text('Using camera Virtual2 as cam0\n')
    (tmp_path / 'stderr').write_text('INFO configuring streams: (0) 400x300-NV12/SMPTE170M\n')
    (tmp_path / 'inferior-exit.json').write_text(json.dumps(dict(exit_code=1, observation_failures=[])))
    with pytest.raises(ValueError, match='Inferior failed'):
        cam.validate_run(tmp_path, camera='Virtual2', configuration='(0) 400x300-NV12/SMPTE170M',
                         executable=tmp_path / 'cam', libraries=[])


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'error-status', 'sequence'])
def test_request_complete_does_not_hide_bad_buffer_metadata(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(cam, 'require_success', lambda _: {})
    monkeypatch.setattr(cam, 'sha256', lambda _: 'digest')
    executable = tmp_path / 'cam'
    (tmp_path / 'stdout').write_text('Using camera Virtual2 as cam0\n')
    (tmp_path / 'stderr').write_text('INFO configuring streams: (0) 400x300-NV12/SMPTE170M\n')
    (tmp_path / 'inferior-exit.json').write_text(json.dumps(dict(exit_code=0, observation_failures=[])))
    (tmp_path / 'loaded.json').write_text(json.dumps(dict(pid=42, executable=str(executable.resolve()),
                                                        files={str(executable.resolve()): 'digest'})))
    (tmp_path / 'allocations.jsonl').write_text(json.dumps(dict(result=5, backing_fd=4, providers={'3': '/dev/udmabuf'},
                                                              fdinfo='exp_name:\tudmabuf\n')) + '\n')
    entries = [dict(point=point, request=str(i), sequence=i, status=1, tid=tid)
               for i in range(3) for point, tid in [('callback-entry', 12), ('frame-processed', 11)]]
    (tmp_path / 'events.jsonl').write_text('\n'.join(map(json.dumps, entries)))
    buffers = [dict(request=str(i), sequence=i, status=1, buffer_status=0, buffer_sequence=i) for i in range(3)]
    if failure == 'missing':
        buffers.pop()
    elif failure == 'duplicate':
        buffers[-1] = buffers[0]
    elif failure == 'error-status':
        buffers[0]['buffer_status'] = 1
    else:
        buffers[0]['buffer_sequence'] = 8
    (tmp_path / 'buffers.jsonl').write_text('\n'.join(map(json.dumps, buffers)))
    with pytest.raises(ValueError, match='frame-buffer metadata'):
        cam.validate_run(tmp_path, camera='Virtual2', configuration='(0) 400x300-NV12/SMPTE170M',
                         executable=executable, libraries=[])
