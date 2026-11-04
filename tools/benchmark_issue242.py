"""Compare existing/new decisions on the same controlled matrix, no model API.

Run: python tools/benchmark_issue242.py --baseline-ref <commit> --out build/issue242-bench
The explicit baseline is archived; neither receipts nor Git refs are edited.
The baseline must include #214's publication plan, generation journal and CLI
checkpoints (for this issue: 83c83158dfd1ff876a4c52ae3db8e56fdc1aaae5).
The helper verifies identical call expectations, quality and archive preservation
in both subprocesses. Decision-specific assertions remain in normal pytest.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(out, code):
    sys.path.insert(0, str(ROOT/'tests'))
    import pytest
    import conftest
    import test_generated_design as fixtures
    from test_issue242_decisions import CASES, exercise_fixed_input
    import sdd
    if not Path(sdd.__file__).resolve().is_relative_to(code.resolve()):
        raise RuntimeError('Benchmark imported the wrong source tree')
    results=[]
    started=time.perf_counter()
    for case, expected in CASES:
        work=out/case
        work.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            cfg=conftest.tmp_cfg.__wrapped__(work)
            generated=fixtures.generated.__wrapped__(cfg)
            units=fixtures.cli_units.__wrapped__(generated,cfg,patch)
            row=exercise_fixed_input(units,cfg,patch,case,expected)
            results.append(row)
            (out/'results.json').write_text(json.dumps(dict(
                transport='controlled CLI double; no actual inference',code_root=str(code),
                worker_wall_seconds=time.perf_counter()-started,cases=results),ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--code',type=Path)
    parser.add_argument('--baseline-ref',help='Explicit immutable baseline commit, required outside worker mode')
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True)
    if args.code:
        worker(out,args.code)
        return
    if not args.baseline_ref or args.baseline_ref.startswith('-'):
        parser.error('--baseline-ref must name the explicit baseline commit')
    baseline=subprocess.run(['git','rev-parse','--verify',args.baseline_ref+'^{commit}'],
                            cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    raw=subprocess.run(['git','archive',baseline,'src'],cwd=ROOT,capture_output=True,check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(out/'baseline-code',filter='data')
    for label,code in [('before',out/'baseline-code/src'),('after',ROOT/'src')]:
        env={**os.environ,'PYTHONPATH':str(code),'PYTHONUTF8':'1'}
        with (out/(label+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,__file__,'--out',str(out/label),'--code',str(code)],
                           cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    before=json.loads((out/'before/results.json').read_text(encoding='utf-8'))
    after=json.loads((out/'after/results.json').read_text(encoding='utf-8'))
    rows=[]
    for old,new in zip(before['cases'],after['cases'],strict=True):
        if old['case']!=new['case'] or old['fixed_input_sha256']!=new['fixed_input_sha256']:
            raise ValueError('Representative input changed between measurements')
        if old['quality'] != new['quality']:
            raise ValueError(f"Quality changed between measurements: {old['case']}")
        keys=('new_generation','new_grounding','new_visual','new_translation')
        rows.append(dict(case=old['case'],fixed_input_sha256=old['fixed_input_sha256'],
            before_calls={k:old[k] for k in keys},after_calls={k:new[k] for k in keys},
            before_seconds=old['seconds'],after_seconds=new['seconds'],
            quality_identical=old['quality']==new['quality'],quality=new['quality'],
            before_forecast=old['forecast'],after_forecast=new['forecast'],
            original_archives_preserved=[old['original_archives_preserved'],new['original_archives_preserved']]))
    (out/'comparison.json').write_text(json.dumps(dict(
        baseline_commit=baseline,transport='controlled CLI double; actual selected-CLI results are separate',cases=rows,
        before_worker_wall_seconds=before['worker_wall_seconds'],after_worker_wall_seconds=after['worker_wall_seconds'],
        limitations='Per-case seconds cover the second generate/translate/export/verify only. Worker wall includes setup. No model inference or full-publication speedup is measured.'
    ),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{k:r[k] for k in ('case','before_calls','after_calls','before_seconds','after_seconds','quality_identical')} for r in rows],indent=2))


if __name__=='__main__':
    main()
