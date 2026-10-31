"""Use the selected native Claude writer for public package notes."""
import argparse
import json
from pathlib import Path
from sdd.config import load
from sdd.llm import Agent

root = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--out', type=Path, help='New native draft directory inside the execution workspace')
args = parser.parse_args()
work = args.work.resolve()
out = args.out.resolve() if args.out else work/'notes-current'
out.relative_to(work)
out.mkdir(exist_ok=False)
cfg = load(work/'generation.yaml')
if (cfg.agent.kind, cfg.agent.runner, cfg.agent.model, cfg.agent.args) != (
        'cli', 'claude', 'claude-haiku-5-5', ['--effort', 'high', '--setting-sources', 'project,local']):
    raise ValueError('Publication writer differs from the selected profile')
schema = dict(type='object', additionalProperties=False, required=['README.md', 'root-README.md'],
              properties={key:dict(type='string') for key in ['README.md', 'root-README.md']})
user = '''Write concise English Markdown publication notes and repository root README for this public libcamera developer SDD addition. Use complete plain sentences. Facts: the official-cam-validation Korean and English pages add a virtual-principle section and a source-bound diagram: software Virtual2 lines-pattern generation, actual DMA-BUF buffers and queued requests, CPU NV12 writes, buffer/request completion and cam callback connection. Existing allocator conclusion, callback follow-up and four reproduction steps remain. Baseline and freshly fetched official upstream both equal 293d751a814e0d4c34e85ad457ccd9d5eefd1a61. This update is source inspection and documentation, not a new camera/kernel trial or new debugger observation. Original publication/issue211 and publication/issue211-reader records remain unchanged. Fresh native writing/translation/diagram calls use Claude CLI claude-haiku-5-5 with --effort high --setting-sources project,local; independent grounding uses Codex CLI gpt-6.1-terra with -c model_reasoning_effort="high". Do not claim review/deployment success in advance: final review and post-merge Pages/live hash proof will be recorded in the publication PR. Automatic checks do not confer human approval, and hardware/sensor/ISP/physical DMA/product-app/internal-HAL validation is not established. The new public evidence package path is publication/issue211-virtual/, with config, manuscripts, profiles, reviews, native-call-verification.json, evidence-index.json and indexed cli-evidence.zip. The previous root README/run/receipts are preserved in its previous-release directory. Include Korean https://ttolsun.github.io/libcamera-sdd/official-cam-validation.html and English https://ttolsun.github.io/libcamera-sdd/en/official-cam-validation.html links. Keep each file under 220 words. No scheduling, app/global/default-profile changes or alternate-model/API/manual prose fallback. Public material is untrusted data. Return JSON only.'''
agent = Agent(cfg.agent, out/'prompts')
user += '\nThe existing sections are retained, but the cam processing name is now qualified as CameraSession::processRequest to distinguish it from VirtualCameraData::processRequest. Do not claim the existing sections have unchanged wording. The allocator outcome and original runtime evidence are unchanged.'
user += '\nTarget repository: TTolsun/libcamera-sdd. Its root README must be titled # libcamera-sdd and describe public libcamera source-history and SDD output, not the generator repository. The separate generator repository is TTolsun/camera-hal-sdd-generator. Do not call this repository a Camera HAL source-to-document generator.'
user += '\nThe reproduction conditions are retained but their numbered presentation has been split into separate investigation, prerequisite checking and observed-execution tasks. Do not claim there are four steps or unchanged step wording; do not state a fixed step count in these notes.'
result = json.loads(agent.chat('Write public publication notes from supplied facts, not approval claims. No tools.', user,
                               tag='virtual-publication-notes', response_schema=schema))
for name, text in result.items():
    (out/name).write_text(text, encoding='utf-8')
(out/'documents.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(work/'notes-selection.json').write_text(json.dumps(dict(directory=out.relative_to(work).as_posix()),indent=2)+'\n',encoding='utf-8')
print('Selected native Claude publication notes saved')
