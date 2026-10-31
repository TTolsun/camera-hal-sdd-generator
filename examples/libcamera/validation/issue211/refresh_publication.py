"""Preserve first drafting inputs, then bind the final metadata-observed series."""
import json
from pathlib import Path
import shutil

import yaml
from sdd.runtime_evidence import sha256

root = Path(__file__).resolve().parents[4]
work = root / 'build/issue211-publication'
saved = root / 'examples/libcamera/validation/issue211/runs/20261031-first-document-inputs'
saved.mkdir(exist_ok=False)
for source in [work / 'config/product-evidence/official-cam-observation.json', work / 'config/sections.yaml',
               work / 'run/facts/facts.json', work / 'config/products.yaml']:
    shutil.copyfile(source, saved / source.name)
runtime = root / 'examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3'
material = work / 'config/product-evidence/official-cam-observation.json'
summary = json.loads(material.read_text(encoding='utf-8'))
observed = json.loads((runtime / 'observation.json').read_text(encoding='utf-8'))
for key in ['results', 'binaries', 'kernel', 'uid', 'gid', 'status']:
    summary[key] = observed[key]
summary['run_threads'] = []
summary['buffer_metadata'] = []
for i, result in enumerate(observed['results'], 1):
    events = [json.loads(line) for line in (runtime / f'cam-{i}/events.jsonl').read_text().splitlines()]
    summary['run_threads'].append(dict(pid=result['pid'], callbacks=sorted({e['tid'] for e in events if e['point']=='callback-entry'}),
                                       processed=sorted({e['tid'] for e in events if e['point']=='frame-processed'})))
    summary['buffer_metadata'].append([json.loads(line) for line in (runtime / f'cam-{i}/buffers.jsonl').read_text().splitlines()])
summary.update(pretrial_kernel='6.18.33.2-microsoft-standard-WSL2', pretrial_udmabuf=False,
               pretrial_dmabuf_heaps=False, pretrial_provider_devices_present=False,
               source_unmodified=True, kernel_trial_authorized_by_user=True,
               restored_kernel=(root / 'build/issue211-kernel-trial-2/restore-boot/stdout').read_text().strip(),
               restored_wslconfig_exists=(Path.home()/'.wslconfig').exists(),
               raw_evidence='https://github.com/TTolsun/camera-hal-sdd-generator/tree/main/examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3')
material.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
path = work / 'config/products.yaml'
data = yaml.safe_load(path.read_text(encoding='utf-8'))
entry = next(e for e in data['evidence'] if e['id']=='official-cam-run')
entry.update(version=sha256(runtime/'observation.json'), sha256=sha256(material))
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
path = work / 'config/sections.yaml'
data = yaml.safe_load(path.read_text(encoding='utf-8'))
data['sections'][-1] = yaml.safe_load(Path(__file__).with_name('official-cam-section.yaml').read_text(encoding='utf-8'))
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
