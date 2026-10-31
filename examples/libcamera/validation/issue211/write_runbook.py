"""Generate documentation only through the issue-selected native Claude CLI."""
import argparse
import json
from pathlib import Path

from sdd.config import load
from sdd.llm import Agent

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
style = '\n\n'.join((root/'style'/name).read_text(encoding='utf-8') for name in ['README.md', 'i-have-adhd.md', 'fluent-korean.md'])
material = (root/'build/issue211-publication/config/product-evidence/official-cam-observation.json').read_text(encoding='utf-8')
command = '''PYTHONPATH=<generator>/src python3 <generator>/examples/libcamera/runtime/run_cam.py \
  --source <unmodified-source-at-293d751a> --build <its-debug-meson-build> \
  --tools <private-extracted-tools-prefix> --probe <compiled-dmabuf-probe> --out <new-evidence-directory>'''
agent = Agent(load(Path(__file__).with_name('generation-profile.yaml')).agent, args.out/'prompts')
text = agent.chat('Write the requested reusable technical Markdown from supplied factual records. No tools.\n'+style,
                 'Write a concise Korean runbook, roughly 600-1200 Korean characters plus one command block, '
                 'for examples/libcamera/runtime/OFFICIAL_CAM.md. Lead with actual official cam WSL virtual-only result. '
                 'Explain fixed source SHA and debug unmodified build, root-only udmabuf permission, real DMA export '
                 'and CPU RW sync probe, three independent process observations joined by request/sequence/status/TID '
                 'and successful buffer metadata. Explain that the packaged kernel is restored and does not expose the allocator; '
                 'the previous successful trial does not mean the default kernel now supports it. Shared kernel/.wslconfig/shutdown '
                 'requires separate host approval, exact backup/rollback proposal and stopped Docker; no modules are installed. '
                 'Do not tell readers to run kernel_trial.py automatically. '
                 'Use the supplied CLI command with placeholders in a WSL root child context; prefix tools is the directory containing usr/bin/gdb and usr/share/gdb. '
                 'The probe is compiled from dmabuf_probe.c with gcc -std=c11 -Wall -Wextra -Werror -O0 -g. '
                 'Mention timeouts/failures stay failed and previous output directories cannot be overwritten. '
                 'Bound physical DMA/camera/other product apps/internal HAL and human approval as unvalidated; GDB is not timing/return proof. '
                 'End with a link to README.md for the historical CPU-only probe and a relative link ../validation/issue211/runs/20261031-wsl-cam-3/observation.json. '
                 'TID is NOT an equality join key: join by PID/request/sequence, then compare status and record differing TIDs. '
                 'Scope errno 13 only to the observed test-kernel run. Put supported allocator/kernel and separate host approval BEFORE the capture command. '
                 'Do not include source line numbers, compiler-diff location claims, cleanup event counts or tables. '
                 'Use at most five numbered preparation/execution steps and three short result/scope paragraphs. '
                 'Return JSON with a markdown field containing the COMPLETE concise runbook, maximum 3500 characters.\nCOMMAND\n'+command+'\nACTUAL EVIDENCE\n'+material,
                 tag='official-cam-runbook', response_schema={'type':'object','additionalProperties':False,
                  'required':['markdown'],'properties':{'markdown':{'type':'string','maxLength':3500}}})
text = json.loads(text)['markdown']
if len(text) > 3500:
    raise ValueError('Runbook exceeded the requested complete-document length')
(args.out/'OFFICIAL_CAM.md').write_text(text+'\n', encoding='utf-8')
print(agent.last_receipt)
