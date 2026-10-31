"""Derive a bounded reader input; preserve the complete original measurements."""
from pathlib import Path
import json
import copy
import yaml
from sdd.config import load
from sdd.facts.model import KnowledgeModel
from sdd.evidence import collect
from sdd.runtime_evidence import sha256

root=Path(__file__).resolve().parents[4]
base=Path(__file__).resolve().parent
work=root/'build/issue211-reader'
original=work/'config/product-evidence/official-cam-observation.json'
data=json.loads(original.read_text(encoding='utf-8'))
keys=['schema','source_commit','camera','applied_configuration','status','kernel','results',
      'source_unmodified','allocator','run_threads','inferior_exit_codes','processed_sequences',
      'dma_probe_events','pretrial_kernel','pretrial_udmabuf','pretrial_dmabuf_heaps',
      'pretrial_provider_devices_present','kernel_trial_authorized_by_user',
      'restored_kernel','restored_wslconfig_exists','matching_modules_installed',
      'docker_during_trial','unprivileged_run','observation_limits','physical_dma',
      'physical_camera','production_application','internal_hal','human_review','raw_evidence']
reader={k:data[k] for k in keys}
reader['official_allocator_observations']=[]
for number in range(1,4):
    path=root/f'examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3/cam-{number}/allocations.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    reader['official_allocator_observations'].append(dict(
        pid=rows[0]['pid'],successful_allocations=len(rows),
        providers=sorted({p for row in rows for p in row['providers'].values()}),
        exporters=sorted({line.split(':',1)[1].strip() for row in rows for line in row['fdinfo'].splitlines() if line.startswith('exp_name:')}),
        raw_sha256=sha256(path)))
negative=root/'examples/libcamera/validation/issue211/runs/20261031-runtime-negative/official-cam-debugger-before'
reader['baseline_capture']={
    'inferior_exit':json.loads((negative/'inferior-exit.json').read_text()),
    'errors':[line for line in (negative/'stderr').read_text(encoding='utf-8').splitlines()
              if 'Could not open any dma-buf provider' in line or "Can't allocate buffers" in line],
    'stdout_sha256':sha256(negative/'stdout'),'stderr_sha256':sha256(negative/'stderr'),
    'raw_url':'https://github.com/TTolsun/camera-hal-sdd-generator/tree/580df5156da7066a60e16ff9b656253b1c17f0c0/examples/libcamera/validation/issue211/runs/20261031-runtime-negative/official-cam-debugger-before'}
reader['source_measurement']={
    'sha256':sha256(original),
    'url':'https://github.com/TTolsun/libcamera-sdd/blob/d36affef9b3a741581d1c5f0f4cd68425c5dbe15/publication/issue211/config/product-evidence/official-cam-observation.json',
    'operation':'Exact projection of named original fields, no new runtime execution'}
material=work/'config/product-evidence/official-cam-reader.json'
material.write_text(json.dumps(reader,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=work/'config/products.yaml';products=yaml.safe_load(p.read_text(encoding='utf-8'))
entry=copy.deepcopy(next(e for e in products['evidence'] if e['id']=='official-cam-run'))
entry.update(id='official-cam-reader',file='product-evidence/official-cam-reader.json',sha256=sha256(material),version=sha256(original))
products['evidence']=[e for e in products['evidence'] if e['id']!='official-cam-reader']+[entry]
feature=next(p for p in products['products'] if p['id']=='libcamera-official-cam-trial')['features'][0]
feature['evidence']=['official-cam-reader','execution-contract']
p.write_text(yaml.safe_dump(products,allow_unicode=True,sort_keys=False),encoding='utf-8')
p=work/'config/sections.yaml';sections=yaml.safe_load(p.read_text(encoding='utf-8'))
replacement=yaml.safe_load((base/'section.yaml').read_text(encoding='utf-8'))
sections['sections']=[replacement if s['id']==replacement['id'] else s for s in sections['sections']]
p.write_text(yaml.safe_dump(sections,allow_unicode=True,sort_keys=False,width=130),encoding='utf-8')
cfg=load(work/'generation.yaml');model=KnowledgeModel.load(cfg.facts_path)
assert model.meta['source_commit']=='293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
collect(cfg,model);model.save(cfg.facts_path)
print('bounded measurement bytes',material.stat().st_size)
