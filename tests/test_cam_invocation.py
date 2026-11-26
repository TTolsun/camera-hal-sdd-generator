"""The preview must stay read-only and match the recorded official invocation."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'examples/libcamera/runtime'
# Raw run records are excluded from the in-house import kit, so the recorded
# cam arguments are pinned here and checked against the record when present.
HISTORICAL = ROOT / 'examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3/cam-1/record.json'
RECORDED_CAM_ARGS = ['--camera', 'Virtual2', '--capture=3', '--stream',
                     'role=video,width=400,height=300,pixelformat=NV12']


def test_pinned_arguments_match_original_capture_record():
    if not HISTORICAL.exists():
        assert (ROOT / 'IMPORT-MANIFEST.json').is_file(), f'missing raw record: {HISTORICAL}'
        return  # import kit: the raw record is intentionally not packaged
    argv = json.loads(HISTORICAL.read_bytes())['argv']
    assert argv[argv.index('--args') + 2:] == RECORDED_CAM_ARGS


def test_preview_is_read_only_and_matches_original_capture(tmp_path):
    build = tmp_path / 'nonexistent-build'
    isolated = tmp_path / 'runtime'
    isolated.mkdir()
    for name in ['preview_cam.py', 'cam_invocation.py']:
        (isolated / name).write_bytes((RUNTIME / name).read_bytes())
    result = subprocess.run([sys.executable, str(isolated / 'preview_cam.py'),
                             '--build', str(build)], check=True, capture_output=True, text=True)
    plan = json.loads(result.stdout)
    assert plan['executed'] is False
    assert not build.exists()
    assert sorted(p.name for p in isolated.iterdir()) == ['cam_invocation.py', 'preview_cam.py']
    assert plan['cam_argv'][1:] == RECORDED_CAM_ARGS
    assert plan['cam_argv'][0] == str(build.resolve() / 'src/apps/cam/cam')
