"""Independent Terra review of actual implementation/test bytes."""
import argparse
import json
from pathlib import Path

from sdd.config import load
from sdd.llm import Agent
from sdd.runtime_evidence import sha256

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
files = [root / name for name in ['src/sdd/runtime_evidence.py', 'examples/libcamera/runtime/dmabuf_probe.c',
                                  'examples/libcamera/runtime/observe_cam.gdb.py', 'examples/libcamera/runtime/run_cam.py',
                                  'tests/test_runtime_evidence.py', 'tests/test_official_cam_evidence.py']]
content = '\n\n'.join(str(p.relative_to(root)) + '\n' + p.read_text(encoding='utf-8') for p in files)
schema = {'type': 'object', 'additionalProperties': False, 'required': ['verdict', 'findings', 'scope'],
          'properties': {'verdict': {'enum': ['pass', 'needs-revision']}, 'findings': {'type': 'array', 'items': {'type': 'string'}},
                         'scope': {'type': 'string'}}}
agent = Agent(load(Path(__file__).with_name('independent-review-profile.yaml')).agent, args.out / 'prompts')
answer = json.loads(agent.chat('Review implementation correctness and concrete false-success paths. Return JSON. No tools.',
                               'Review these exact files for issue211: real udmabuf export, RW sync brackets, actual volatile CPU access, '
                               'failure/timeout/cleanup, immutable raw evidence, identity/config/thread/callback matching, and no success '
                               'on missing/duplicate callbacks, ioctl errors, configuration mismatch, or debugger=0/inferior!=0. '
                               'Look for actionable bugs in implemented paths, not speculative future features. Report gaps honestly.\n' + content,
                               tag='implementation-review', response_schema=schema))
(args.out / 'review.json').write_text(json.dumps(dict(review=answer, inputs={str(p.relative_to(root)): sha256(p) for p in files},
                                                    receipt=str(agent.last_receipt)), indent=2) + '\n', encoding='utf-8')
print(answer['verdict'], flush=True)
