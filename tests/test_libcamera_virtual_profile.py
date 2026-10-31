"""The public trial baseline cannot be silently replaced by another source."""
import json
from pathlib import Path
import subprocess
import sys


def test_virtual_addition_rejects_another_commit_before_creating_output(tmp_path):
    previous = tmp_path/'earlier-run'
    facts = previous/'run/facts/facts.json'
    facts.parent.mkdir(parents=True)
    original = json.dumps(dict(meta=dict(source_commit='a'*40))).encode()
    facts.write_bytes(original)
    work = tmp_path/'new-run'
    script = Path(__file__).resolve().parents[1]/'examples/libcamera/validation/issue211-virtual/prepare.py'
    result = subprocess.run([sys.executable, str(script), '--previous', str(previous), '--work', str(work)],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'commits must not be mixed' in result.stderr
    assert not work.exists()
    assert facts.read_bytes() == original
