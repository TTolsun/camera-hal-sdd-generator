"""Inspect immutable public evidence without treating archived calls as new calls."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[4]
ARCHIVES = {
    '07': '77b8151e4d30c3a6d9a9ad6266dc4a0ff14ac1b68fc110d85ff6fec5d033c07b',
    '08': '6a94dfbdda4d40ef63079d9ed60ecec58c67c63ad12a76dc47a451f4f32a08c5',
}
SCOPES = {
    '07': ['refinement-runs-15/vendor-assurance/step-01/',
           'refinement-runs-16/vendor-assurance/step-01/',
           'refinement-runs-19/ipa/step-01/'],
    '08': ['refinement-runs-21/ipa/step-01/', 'refinement-runs-23/ipa/step-01/'],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect(destination):
    destination.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, source_commit='293d751a814e0d4c34e85ad457ccd9d5eefd1a61',
                  mode='historical-inspection', new_cli_calls=0, human_review='pending',
                  archives=[], calls=[], reviews=[], failures=[], plans=[])
    for number, expected in ARCHIVES.items():
        path = ROOT / f'docs/libcamera/records/issue215/native-evidence-{number}.tar.xz'
        if sha(path.read_bytes()) != expected:
            raise ValueError(f'Archive checksum mismatch: {path}')
        report['archives'].append(dict(path=path.relative_to(ROOT).as_posix(), sha256=expected))
        with tarfile.open(path) as archive:
            members = {m.name: m for m in archive.getmembers() if m.isfile()}

            def read(name):
                return archive.extractfile(members[name]).read()

            def binding(name):
                return dict(archive=number, member=name, sha256=sha(read(name)))

            for scope in SCOPES[number]:
                prefix = 'build/issue215/' + scope
                for name in members:
                    if not name.startswith(prefix):
                        continue
                    if name.endswith('config/visuals.yaml'):
                        report['plans'].append(binding(name))
                    if name.endswith('.failure.json'):
                        report['failures'].append(dict(**binding(name), failure=json.loads(read(name))))
                    if '/build/prompts/calls/' not in name or not name.endswith('.receipt.json'):
                        continue
                    receipt = json.loads(read(name))
                    if not receipt['tag'].startswith(('visual_vendor-assurance_configuration-contract-validity_',
                                                      'visual_ipa_execution-boundaries_')):
                        continue
                    stem = name.removesuffix('.receipt.json')
                    request_raw, response_raw = read(stem+'.request.json'), read(stem+'.response.txt')
                    request, response = json.loads(request_raw), json.loads(response_raw)
                    request_hash = sha(json.dumps(request, ensure_ascii=False, sort_keys=True).encode())
                    if request_hash != receipt['request_sha256'] or sha(response_raw) != receipt['response_sha256']:
                        raise ValueError(f'Call binding mismatch: {name}')
                    # Preserve the exact original triple once, even when copied between runs.
                    call_dir = destination / 'originals' / sha(read(name))
                    call_dir.mkdir(parents=True, exist_ok=True)
                    for suffix in ['receipt.json', 'request.json', 'response.txt']:
                        (call_dir/suffix).write_bytes(read(stem+'.'+suffix))
                    nodes = response['nodes']
                    nodes = list(nodes.values()) if isinstance(nodes, dict) else nodes
                    labels = defaultdict(list)
                    for item in nodes + response['edges']:
                        labels[item['label']].append(item['label_en'])
                    collisions = {ko: sorted(set(en)) for ko, en in labels.items() if len(set(en)) > 1}
                    report['calls'].append(dict(**binding(name), scope=scope, tag=receipt['tag'],
                        completed_at=receipt['completed_at'], request_sha256=request_hash,
                        response_sha256=sha(response_raw), collisions=collisions,
                        feedback=request['user'].split('\nError: ', 1)[1].split('\nRejected draft:', 1)[0]
                                 if '\nError: ' in request['user'] else None))
            for name in members:
                if name.endswith('materialized-13-vendor-assurance/review.json'):
                    report['reviews'].append(dict(**binding(name), review=json.loads(read(name))))
    report['unique_completed_receipts'] = len({r['sha256'] for r in report['calls']})
    report['copied_receipt_occurrences'] = len(report['calls'])-report['unique_completed_receipts']
    report['limits'] = [
        'Stored plans and copied historical receipts do not prove the current main has the same defect.',
        'An earlier mechanical rejection can hide semantic findings; review13 does not prove they were introduced by retry16.',
        'No missing wall-clock interval, transient cause, semantic resolution or whole-site acceptance is inferred.',
    ]
    (destination/'history.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'build/issue243/history')
    args = parser.parse_args()
    result = inspect(args.output)
    print(json.dumps({k: result[k] for k in ('new_cli_calls', 'unique_completed_receipts',
                                           'copied_receipt_occurrences')}, indent=2))
