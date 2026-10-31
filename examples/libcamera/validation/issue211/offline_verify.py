"""Revalidate current predicates against archived native records; no new capture."""
import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(root/'src'), str(root/'examples/libcamera/runtime')]
from sdd.runtime_evidence import require_success, sha256, validate_dma
from run_cam import validate_run, rows

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
runtime = args.runtime.resolve()
manifest = json.loads((runtime/'observation.json').read_text())
for name, digest in manifest['artifacts'].items():
    if sha256(runtime/name) != digest:
        raise ValueError('Archived evidence changed: ' + name)
require_success(runtime/'dma-probe')
validate_dma(rows(runtime/'dma-probe/stdout'))
build = Path('/home/baboess/.cache/issue211-runtime-D6sfkcnF/build')
results = [validate_run(runtime/f'cam-{index}', camera='Virtual2', configuration='(0) 400x300-NV12/SMPTE170M',
                        executable=build/'src/apps/cam/cam',
                        libraries=[build/'src/libcamera/libcamera.so', build/'src/libcamera/base/libcamera-base.so'])
           for index in range(1, 4)]
(args.out/'verification.json').write_text(json.dumps(dict(schema=1, status='passed',
    scope='Offline current-predicate revalidation of preserved native evidence; not a new capture or human approval',
    original_kernel=manifest['kernel'], original_source_commit=manifest['source_commit'],
    results=results, record_sha256=sha256(runtime/'observation.json')), indent=2)+'\n')
