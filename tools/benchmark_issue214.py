"""No-model enforcement benchmark; run wall clock and cProfile separately."""
import argparse
import cProfile
import json
import importlib.util
from pathlib import Path
import platform
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--historical-validator', type=Path,
                        help='Keep the exact frozen validator/policy and receipts; use current request preparation')
    args = parser.parse_args()
    sys.path.insert(0, str(args.engine.resolve()/'src'))
    from sdd.config import load
    from sdd.facts.model import KnowledgeModel
    from sdd.consistency import enforce
    mode = 'normal-enforcement'
    if args.historical_validator:
        # This is an explicitly isolated performance experiment, not a current
        # policy approval. No report, checkpoint, policy hash or receipt changes.
        path = args.historical_validator/'src/sdd/consistency.py'
        spec = importlib.util.spec_from_file_location('sdd._issue214_frozen', path)
        frozen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(frozen)
        from sdd.consistency import request
        from sdd.validation_stage import staged
        frozen.request = request
        enforce = staged(frozen.enforce)
        mode = 'frozen-full-validator-with-current-input-preparation'
    cfg = load(args.config)
    model = KnowledgeModel.load(cfg.facts_path)
    profile = cProfile.Profile() if args.profile else None
    started = time.perf_counter()
    if profile:
        profile.enable()
    status, error = 'passed', None
    try:
        enforce(cfg, model)
    except Exception as exc:
        status, error = 'failed', f'{type(exc).__name__}: {exc}'
    seconds = time.perf_counter()-started
    if profile:
        profile.disable()
        profile.dump_stats(str(args.out.with_suffix('.prof')))
    result = dict(status=status, error=error, seconds=seconds, profiled=bool(profile),
                  python=sys.version, platform=platform.platform(),
                  engine=str(args.engine.resolve()), source_commit=model.meta['source_commit'],
                  model_calls=0, mode=mode)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    if error:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
