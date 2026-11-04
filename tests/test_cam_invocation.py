"""The preview must stay read-only and match the recorded official invocation."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'examples/libcamera/runtime'


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
    historical = ROOT / 'examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3/cam-1/record.json'
    argv = json.loads(historical.read_bytes())['argv']
    original = argv[argv.index('--args') + 1:]
    assert plan['cam_argv'][1:] == original[1:]
    assert plan['cam_argv'][0] == str(build.resolve() / 'src/apps/cam/cam')
