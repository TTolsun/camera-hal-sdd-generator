"""Collect measured evidence, preserving failed and synthetic/real boundaries."""
import hashlib
import json
from pathlib import Path
import pstats
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'build/issue214'
OUT = ROOT/'docs/records/issue214'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    benchmarks = {}
    for name in ('before-wall', 'before-profile', 'optimized-historical-wall',
                 'optimized-historical-profile', 'after-wall'):
        path = WORK/(name+'.json')
        if path.exists():
            row = json.loads(path.read_bytes())
            row.pop('engine', None)
            benchmarks[name] = row
    profiles = {}
    for name in ('before-profile', 'optimized-historical-profile'):
        path = WORK/(name+'.prof')
        if not path.exists():
            continue
        rows = []
        stats = pstats.Stats(str(path))
        for (file, line, function), (primitive, calls, own, cumulative, callers) in stats.stats.items():
            if function in ('safe_load', 'sections', '_sections', 'request', '_request', 'enforce', '_next', 'checked_footer'):
                rows.append(dict(file=Path(file).name, function=function, calls=calls,
                                 primitive_calls=primitive, own_seconds=own, cumulative_seconds=cumulative))
        profiles[name] = sorted(rows, key=lambda row: -row['cumulative_seconds'])
    matrix = []
    for path in sorted((WORK/'test-final-focused').rglob('matrix-*.json')):
        row = json.loads(path.read_bytes())
        # Older local runs used an imprecise label; these were controlled
        # grounding doubles, never independent native review calls.
        if 'new_independent_reviews' in row:
            row['new_grounding_reviews'] = row.pop('new_independent_reviews')
        matrix.append(row)
    archives = {path.name: dict(bytes=path.stat().st_size, sha256=sha(path))
                for path in sorted((WORK/'archives').glob('*.zip'))}
    inputs = {str(path.relative_to(WORK/'fixture')): sha(path)
              for path in sorted((WORK/'fixture/config').rglob('*')) if path.is_file()}
    for name in ('publication.yaml', 'independent-review.yaml', 'run/english.json', 'run/facts/facts.json'):
        inputs[name] = sha(WORK/'fixture'/name)
    result = dict(schema=1, benchmarks=benchmarks, profiles=profiles, controlled_cli_matrix=matrix,
        archives=archives, restored_effective_inputs=inputs,
        fixed_generator='ea5fa4c1b4eb2748d373cc911c3d4c67e87a93a1',
        fixed_source='293d751a814e0d4c34e85ad457ccd9d5eefd1a61',
        fixed_sdd='85b4cd8d6fd9e1778eac3f20cbd0df0e6b8b7cf3',
        interpretation='Historical full validation uses unchanged archived policy and receipts with current preparation. '
        'It is not a current-policy approval. Failed normal current enforcement remains a failure. '
        'Controlled matrix calls are transport doubles, not native document drafting or independent review.')
    (OUT/'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    payload = WORK/'payload-comparison.json'
    if payload.exists():
        (OUT/payload.name).write_bytes(payload.read_bytes())
    print('Collected available measurements without promoting incomplete steps.', flush=True)


if __name__ == '__main__':
    main()
