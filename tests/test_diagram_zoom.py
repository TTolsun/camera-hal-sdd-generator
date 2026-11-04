"""Viewer lifecycle policy; real SVG layout is checked in the browser."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_readable_zoom_and_explicit_fit():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the viewer lifecycle regression check')
    result = subprocess.run([node, str(ROOT / 'tests/js/diagram_zoom.cjs')],
                            cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
