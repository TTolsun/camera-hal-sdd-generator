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


def test_publication_notes_reject_mixed_baseline_before_creating_draft(tmp_path):
    work = tmp_path/'run'
    work.mkdir()
    record = work/'upstream.json'
    original = json.dumps(dict(baseline='a'*40, observed_upstream='b'*40, unchanged=False)).encode()
    record.write_bytes(original)
    output = work/'new-notes'
    script = Path(__file__).resolve().parents[1]/'examples/libcamera/validation/issue211-virtual/notes.py'
    result = subprocess.run([sys.executable, str(script), '--work', str(work), '--out', str(output),
                             '--upstream-record', str(record)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'Invalid baseline/upstream distinction' in result.stderr
    assert not output.exists()
    assert record.read_bytes() == original
