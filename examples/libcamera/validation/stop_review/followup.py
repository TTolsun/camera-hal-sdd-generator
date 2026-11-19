"""Run the pinned stop-review benchmark with change-aware child reviews."""
import argparse
import copy
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'src'))
from sdd import independent_review
from sdd.change_review import change_review_instructions

ORIGINAL = '53633e89a05720e23031a3985682a65f76681281a964db36097748c33a47642a'
INDEXES = {
    'candidates.json': '339ec595a38c1c09c7fdbb4ba657b9fbf019236f55f0a1247429f1229929be91',
    'assessments.json': '83da0e03e594d2c448e2331350c410403c9c98e795b0773fa0d3edb1c18d1ff1',
}


def pinned_bytes(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'SHA-256 mismatch for pinned input {path}')
    return data


def load_original(path):
    source = pinned_bytes(path, ORIGINAL)
    spec = importlib.util.spec_from_file_location('_pinned_stop_review', path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot import the original Python script at {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def install_attempt(origin, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if origin.is_symlink() or any(path.is_symlink() for path in origin.rglob('*')):
        raise ValueError(f'Imported attempt contains a symbolic link: {origin}')
    with TemporaryDirectory(dir=target.parent) as temp:
        staged = Path(temp) / target.name
        shutil.copytree(origin, staged)
        staged.rename(target)


def run(args, original, *, indexes=None, policy_identity=None):
    workers = getattr(args, 'workers', 1)
    arm = getattr(args, 'arm', 'both')
    if workers < 1:
        raise ValueError('--workers must be at least 1')
    if arm not in ('both', 'incremental', 'full'):
        raise ValueError('--arm must be both, incremental, or full')
    arms = ('incremental', 'full') if arm == 'both' else (arm,)
    phases = ('prepare', 'baseline', *arms)
    original.PHASES = phases

    out, baseline, git = (getattr(args, name).resolve() for name in ('out', 'baseline_run', 'git'))
    for source in (baseline, git):
        if not source.is_dir() or source == out or source in out.parents or out in source.parents:
            raise ValueError(f'Expected an existing input directory disjoint from --out: {source}')
    digests = INDEXES if indexes is None else dict(INDEXES, **indexes)
    if digests.keys() != INDEXES.keys() or digests['candidates.json'] != INDEXES['candidates.json']:
        raise ValueError('Only the parent assessment digest may be replaced')
    indices = {name: pinned_bytes(baseline / 'baseline' / name, digest)
               for name, digest in digests.items()}
    drafts, reviews = (original.parse_json(indices[name]) for name in INDEXES)
    if any(not isinstance(index, dict) or set(index) != set(original.QUESTIONS)
           for index in (drafts, reviews)):
        raise ValueError('Pinned baseline indices do not cover the original questions')

    class Followup(original.Benchmark):
        def request(self, snapshot, unit, candidate=None):
            request = super().request(snapshot, unit, candidate)
            if snapshot == 'child' and candidate is not None:
                parent = self.get_sources()['parent']['units'][unit]
                prefix = change_review_instructions(parent, request['evidence'])
                if prefix:
                    prompt = prefix.encode('utf-8') + b'\n' + request['prompt']
                    key_data = dict(request['record']['key_data'], prompt_sha256=original.sha256(prompt))
                    request = dict(request, prompt=prompt, record={'key_data': key_data,
                                   'key': original.sha256(original.json_bytes(key_data))})
            return request

        def review_arm(self, phase):
            if workers == 1:
                return super().review_arm(phase)

            candidates = self.frozen_candidates()

            def review(item):
                unit, candidate = item
                worker = copy.copy(self)
                worker.frozen_candidates = lambda: {unit: candidate}
                return original.Benchmark.review_arm(worker, phase)

            independent_review.schedule_reviews(review, candidates.items(), workers=workers)

        def baseline(self):
            historical = original.Benchmark(baseline, self.git, self.executable)
            historical.identity = self.identity
            historical.sources = self.get_sources()
            for unit in original.QUESTIONS:
                draft_request = historical.request('parent', unit)
                draft, _ = historical.validate_proof(drafts[unit], 'baseline', 'draft', unit, draft_request)
                review_request = historical.request('parent', unit, draft)
                historical.validate_proof(reviews[unit], 'baseline', 'review', unit, review_request)
                for kind, proof, request in (('draft', drafts[unit], draft_request),
                                             ('review', reviews[unit], review_request)):
                    path = proof['attempt']
                    install_attempt(baseline / path, self.out / path)
                    self.validate_proof(proof, 'baseline', kind, unit, request)
            for name, data in indices.items():
                path = self.out / 'baseline' / name
                if path.exists():
                    if path.read_bytes() != data:
                        raise ValueError(f'Imported index differs from its pinned input: {path}')
                else:
                    original.atomic_write(path, data)

    marker = out / 'followup.json'
    if args.resume:
        if not marker.is_file():
            raise ValueError('--resume requires a run initialized by this adapter')
    else:
        out.mkdir(parents=True, exist_ok=False)
        original.atomic_write(out / '.gitignore', b'*\n')
    with original.run_lock(out / 'run.lock'):
        benchmark = Followup(out, original.LocalGit(git), original.codex_executable())
        benchmark.record_execution()
        identity = {'execution': benchmark.identity, 'git': str(git),
                    'baseline': str(baseline), 'script': str(args.original_script.resolve()),
                    'original_sha256': ORIGINAL, 'indices': digests,
                    'workers': workers, 'arm': arm,
                    'adapter_sha256': original.file_sha256(Path(__file__)),
                    'context_sha256': original.file_sha256(Path(sys.modules[change_review_instructions.__module__].__file__)),
                    'scheduler_sha256': original.file_sha256(Path(independent_review.__file__))}
        if policy_identity is not None:
            identity['quality_policy'] = policy_identity
        identity = original.json_bytes(identity)
        if args.resume:
            if marker.read_bytes() != identity:
                raise ValueError('Run inputs or execution identity changed. Use a new --out.')
        else:
            original.atomic_write(marker, identity)
        try:
            benchmark.execute_phase('prepare')
            if benchmark.phase_done('baseline'):
                benchmark.baseline()
            else:
                benchmark.execute_phase('baseline')
            for phase in arms:
                if benchmark.phase_done(phase):
                    for unit, candidate in benchmark.frozen_candidates().items():
                        request = benchmark.request('child', unit, candidate)
                        decision = out / phase / 'decisions' / (unit + '.json')
                        benchmark.read_existing_decision(phase, unit, request, decision)
                else:
                    benchmark.execute_phase(phase)
        finally:
            original.write_report(benchmark)
            path = out / 'report.json'
            report = original.read_json(path)
            report['phases'] = {phase: result for phase, result in report['phases'].items()
                                if phase in phases}
            result = report['phases']['baseline']
            attempts = result['attempts']
            result.update(original.sum_calls_and_tokens([]), attempts=[], fresh_calls=0,
                          common_reuse={'imported_attempts': len(attempts), 'attempts': attempts})
            original.write_json(path, report, replace=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('original-script', 'baseline-run', 'git', 'out'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--arm', choices=('both', 'incremental', 'full'), default='both')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be at least 1')
    try:
        original = load_original(args.original_script.resolve())
    except (OSError, ImportError, ValueError) as error:
        parser.exit(1, f'Cannot load original benchmark: {error}\n')
    try:
        run(args, original)
    except KeyboardInterrupt:
        return 130
    except (original.BenchmarkError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print('Follow-up stopped. ' + original.exception_label(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
