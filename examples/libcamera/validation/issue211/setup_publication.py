"""Rebuild from current public inputs; preserve every historical measurement."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import yaml

from sdd.runtime_evidence import sha256

root = Path(__file__).resolve().parents[4]
published = root / 'build/libcamera-sdd-issue211/publication/issue193'
workspace = root / 'build/issue211-publication'
workspace.mkdir(exist_ok=False)
shutil.copytree(published / 'config', workspace / 'config')
shutil.copytree(published / 'manuscripts', workspace / 'run/manuscripts')
(workspace / 'run/facts').mkdir()
(workspace / 'run/facts/facts.json').write_bytes(gzip.decompress((published / 'facts293.json.gz').read_bytes()))
shutil.copyfile(published / 'english.json', workspace / 'run/english.json')
shutil.copyfile(published / 'site-intro.md', workspace / 'site-intro.md')
with zipfile.ZipFile(published / 'cli-evidence.zip') as archive:
    for name in archive.namelist():
        if name.startswith('latest293/build/') and not name.endswith('/'):
            target = workspace / name.removeprefix('latest293/')
            if not target.resolve().is_relative_to(workspace.resolve()):
                raise ValueError('Unsafe historical archive path')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
shutil.copyfile(published / 'consistency-review.json', workspace / 'build/consistency-review.json')

runtime = root / 'examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3'
observed = json.loads((runtime / 'observation.json').read_text(encoding='utf-8'))
summary = {key: observed[key] for key in ['source_commit', 'kernel', 'results', 'uid', 'gid', 'binaries',
                                         'human_review', 'physical_dma', 'physical_camera', 'production_application', 'internal_hal', 'status']}
summary.update(schema=1, camera='Virtual2', applied_configuration='(0) 400x300-NV12/SMPTE170M',
               official_source_tracked_clean=True, kernel_tag='linux-msft-wsl-6.18.33.2',
               kernel_tag_commit='c21a03b2943d147c280bdf32530d4fe6badfd6bd',
               kernel_sha256='cf23bf492a00a5c7517e221b0d8f742ea3cffa9351823191a5ba5c476ba15460',
               compiler_config_diff='GCC 13.2 to Ubuntu GCC 15.2 capability changes, binutils 2.41 to 2.46, pahole 1.25 to 1.31; full diff preserved',
               matching_modules_installed=False, docker_during_trial='stopped',
               allocator='udmabuf built-in, /dev/udmabuf root-only; permissions unchanged',
               unprivileged_run=dict(status='failed', errno=13),
               dma_probe_events=[json.loads(line) for line in (runtime / 'dma-probe/stdout').read_text().splitlines()],
               run_threads=[dict(pid=r['pid'], callbacks=sorted({e['tid'] for e in [json.loads(line) for line in (runtime / f'cam-{i}/events.jsonl').read_text().splitlines()] if e['point']=='callback-entry'}),
                                processed=sorted({e['tid'] for e in [json.loads(line) for line in (runtime / f'cam-{i}/events.jsonl').read_text().splitlines()] if e['point']=='frame-processed'}))
                            for i, r in enumerate(observed['results'], 1)],
               inferior_exit_codes=[0, 0, 0], processed_sequences=[[0, 1, 2]] * 3,
               timeout_probe=dict(seconds=.5, timed_out=True, exit_code=1, sync_end_return_code=0, munmap_return_code=0,
                                  close_return_codes=[0, 0, 0], process_group_absent=True),
               timeout_cleanup_events=[json.loads(line) for line in (root/'examples/libcamera/validation/issue211/runs/20261031-wsl-cleanup/probe-timeout/stdout').read_text().splitlines()],
               negative_probes=dict(absent_provider_errno=2, unsupported_ioctl_errno=25, exit_codes=[1, 1]),
               supplemental_official_cam_strace=dict(exit_code=0, callback_observation=False),
               restored_kernel=(root / 'build/issue211-kernel-trial-2/restore-boot/stdout').read_text().strip(),
               restored_wslconfig_exists=(Path.home() / '.wslconfig').exists(),
               old_cpu_probe=dict(callbacks=72, dma='unvalidated-provider-and-sync-errors-retained', history_unchanged=True),
               observation_limits=['GDB breakpoints affect timing', 'No callback-return instruction observation', 'Cancellation branch not dynamically exercised; observed count 0 is not forced'],
               reproduction_code='https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/examples/libcamera/runtime/run_cam.py',
               raw_evidence='https://github.com/TTolsun/camera-hal-sdd-generator/tree/main/examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3',
               pretrial_kernel='6.18.33.2-microsoft-standard-WSL2', pretrial_udmabuf=False,
               pretrial_dmabuf_heaps=False, pretrial_provider_devices_present=False,
               source_unmodified=True, kernel_trial_authorized_by_user=True,
               main_tid=[v['pid'] for v in observed['results']],
               request_events=[[json.loads(line) for line in (runtime / f'cam-{i}/events.jsonl').read_text().splitlines()] for i in range(1, 4)],
               buffer_metadata=[[json.loads(line) for line in (runtime / f'cam-{i}/buffers.jsonl').read_text().splitlines()] for i in range(1, 4)],
               observation_points={'callback-entry': 'CameraSession::requestComplete entry',
                                   'frame-processed': 'CameraSession::processRequest immediately before captureCount_++',
                                   'buffer-metadata': 'CameraSession::processRequest after reading FrameMetadata'})
material = workspace / 'config/product-evidence/official-cam-observation.json'
material.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
products_path = workspace / 'config/products.yaml'
products = yaml.safe_load(products_path.read_text(encoding='utf-8'))
conditions = ['Source ' + observed['source_commit'], 'WSL2 custom UDMABUF kernel, root child, Virtual2 400x300 NV12', 'GDB observation; no timing/return/physical/internal HAL qualification']
products['products'].append(dict(id='libcamera-official-cam-trial', scope='project', release=observed['source_commit'],
                               configuration='wsl2-virtual2-official-cam-udmabuf', simulation=True, as_of='2026-10-31',
                               features=[dict(id='wsl-virtual-capture', need='Observe official virtual completion and CPU DMA-BUF access',
                                              usage='Source-pinned public virtual trial', availability='unknown', conditions=conditions,
                                              exclusions=['Physical DMA/camera, other production applications and internal HAL not validated'],
                                              implementation=[], evidence=['official-cam-run', 'execution-contract'], claims=[])]))
products['evidence'].append(dict(id='official-cam-run', type='measurement', supplier='Source-pinned official cam trial; raw events, GDB, syscall and cleanup records',
                                version=sha256(runtime / 'observation.json'), date='2026-10-31', valid_until='2026-10-31',
                                product='libcamera-official-cam-trial', release=observed['source_commit'], configuration='wsl2-virtual2-official-cam-udmabuf',
                                feature='wsl-virtual-capture', conditions=conditions, availability='unknown',
                                file='product-evidence/official-cam-observation.json', sha256=sha256(material)))
contract = workspace/'config/product-evidence/issue211-execution-contract.json'
shutil.copyfile(Path(__file__).with_name('runs')/'20261031-issue-execution-contract.json', contract)
products['evidence'].append(dict(id='execution-contract', type='project-document', supplier='GitHub issue211 execution contract, verbatim selected lines',
                                version='2026-10-31T06:00:33Z', date='2026-10-31', valid_until='2026-10-31',
                                product='libcamera-official-cam-trial', release=observed['source_commit'], configuration='wsl2-virtual2-official-cam-udmabuf',
                                feature='wsl-virtual-capture', conditions=conditions, availability='unknown',
                                file='product-evidence/issue211-execution-contract.json', sha256=sha256(contract)))
products_path.write_text(yaml.safe_dump(products, allow_unicode=True, sort_keys=False), encoding='utf-8')
sections_path = workspace / 'config/sections.yaml'
sections = yaml.safe_load(sections_path.read_text(encoding='utf-8'))
sections['sections'].append(yaml.safe_load(Path(__file__).with_name('official-cam-section.yaml').read_text(encoding='utf-8')))
sections_path.write_text(yaml.safe_dump(sections, allow_unicode=True, sort_keys=False), encoding='utf-8')
config = yaml.safe_load((published / 'profiles/generation.yaml').read_text(encoding='utf-8'))
config['source']['root'] = str(root / 'build/libcamera-source-issue211')
config['source']['compile_commands'] = str(workspace / 'historical-compile-commands-not-reexecuted.json')
for key, name in [('sections_file', 'sections.yaml'), ('consistency_file', 'contracts.yaml'), ('scenarios_file', 'scenarios.yaml'),
                  ('products_file', 'products.yaml'), ('glossary_file', 'glossary.yaml')]:
    config['paths'][key] = str(workspace / 'config' / name)
config['paths'].pop('consistency_review_config', None)
config['paths']['config'] = str(workspace / 'config')
config['paths']['prompts'] = str(root / 'examples/libcamera/prompts')
config['paths']['templates'] = str(root / 'templates')
config['paths']['style'] = str(root / 'style')
config['products']['file'] = str(products_path)
config['agent'] = yaml.safe_load(Path(__file__).with_name('generation-profile.yaml').read_text())['agent']
config['documentation'].setdefault('pages', {})['official-cam-validation.md'] = {'max_markdown_chars': 310000}
config['site'].update(enabled=False, intro=str(workspace / 'site-intro.md'),
                      mermaid_dir=str(root / 'build/libcamera-sdd-issue211/docs/assets/mermaid'))
config['visuals']['file'] = str(workspace / 'config/visuals.yaml')
(workspace / 'generation.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
print(workspace)
