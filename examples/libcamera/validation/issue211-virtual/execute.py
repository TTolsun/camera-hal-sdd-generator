"""Record the selected native CLI and normal publication stages independently."""
import argparse
import re
import sys
from pathlib import Path
from sdd.runtime_evidence import run_recorded, require_success

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=['generate', 'translate', 'export', 'render', 'review'])
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--site', type=Path, required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', args.tag):
    raise ValueError('A unique lowercase execution tag is required')
work, site = args.work.resolve(), args.site.resolve()
reader = root/'examples/libcamera/validation/issue211-reader'
prefix = [sys.executable, '-X', 'utf8']
if args.stage == 'generate':
    command = ['-m', 'sdd.cli', '--config', str(work/'generation.yaml'), 'generate', '--sections', 'official-cam-validation']
elif args.stage == 'translate':
    command = [str(reader/'translate.py'), '--work', str(work), '--out', str(work/'translations'/args.tag)]
elif args.stage == 'export':
    command = ['-m', 'sdd.cli', '--config', str(work/'publication.yaml'), 'export-site', '--out', str(site)]
elif args.stage == 'render':
    command = [str(reader/'render_window.py'), '--work', str(work), '--site', str(site), '--out', str(work/'windows'/args.tag)]
else:
    window = work/'windows'/args.tag
    command = [str(reader/'review.py'), '--work', str(work), '--review-config', str(work/'new-document-review.yaml'),
               '--korean', str(window/'ko.txt'), '--english', str(window/'en.txt'), '--inventory', str(window/'inventory.json'),
               '--out', str(work/'reviews'/args.tag)]
    notes = work/'notes-current/documents.json'
    if not notes.exists():
        notes = work/'notes/documents.json'
    if notes.exists():
        command += ['--notes', str(notes)]
out = work/'executions'/(args.stage+'-'+args.tag)
run_recorded(out, prefix+command, timeout=1800, cwd=root)
require_success(out)
print((out/'stdout').read_text(encoding='utf-8'), end='')
