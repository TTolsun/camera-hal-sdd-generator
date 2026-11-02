"""Attach the historical command projection; never claim a fresh capture."""
from pathlib import Path
import copy
import hashlib
import json
import re
import yaml

BASELINE = '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
FEATURE = 'recorded-no-output-sink'
PROJECTION_SHA256 = '58f37ca820c4c97c55a55cdab58f88fae76edf6b2a9b0ed365fd0552ed33b4c5'
ARGS = ['--camera', 'Virtual2', '--capture=3', '--stream',
        'role=video,width=400,height=300,pixelformat=NV12']


def validate(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROJECTION_SHA256:
        raise ValueError('Historical invocation projection changed; reverify its archived records')
    proof = json.loads(raw)
    if (proof.get('source_commit') != BASELINE or proof.get('new_runtime') is not False
            or proof.get('output_sink_options_requested') is not False
            or not re.fullmatch(r'[0-9a-f]{64}', proof.get('archive_sha256', ''))):
        raise ValueError('Invocation scope requires the pinned historical command evidence')
    records = proof.get('records', [])
    if len(records) != 3:
        raise ValueError('Invocation scope requires three independent command records')
    for number, row in enumerate(records, 1):
        if (row.get('cam_arguments') != ARGS or row.get('exit_code') != 0
                or row.get('archive_entry') != f'generator/issue211/runs/20261031-wsl-cam-3/cam-{number}/record.json'
                or not re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', ''))):
            raise ValueError('Invocation command differs from the recorded no-output-sink case')
    return raw


def attach(work, fixture):
    raw = validate(fixture)  # Reject before changing the workspace.
    path = Path(work)/'config/products.yaml'
    data = yaml.safe_load(path.read_bytes())
    product = next(p for p in data['products'] if p['id'] == 'libcamera-official-cam-trial')
    if any(f['id'] == FEATURE for f in product['features']):
        raise ValueError('Preserve an existing invocation-scope attachment')
    feature = copy.deepcopy(next(f for f in product['features'] if f['id'] == 'wsl-virtual-capture'))
    feature['id'] = FEATURE
    feature['evidence'] = ['invocation-'+eid for eid in feature['evidence']] + ['invocation-options']
    product['features'].append(feature)
    for ident in ['official-cam-reader', 'execution-contract', 'reproduction-procedure']:
        record = copy.deepcopy(next(d for d in data['evidence'] if d['id'] == ident))
        record.update(id='invocation-'+ident, feature=FEATURE)
        data['evidence'].append(record)
    digest = hashlib.sha256(raw).hexdigest()
    record = copy.deepcopy(next(d for d in data['evidence'] if d['id'] == 'official-cam-reader'))
    record.update(id='invocation-options', feature=FEATURE,
                  supplier='SHA-verified original official cam argument records; source-scoped projection',
                  version=digest, file='product-evidence/official-cam-invocation.json', sha256=digest)
    data['evidence'].append(record)
    target = path.parent/record['file']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
