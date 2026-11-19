"""Prepare stricter parent reviews and run one change-aware child benchmark arm."""
import argparse
from pathlib import Path, PurePosixPath
import stat
import sys

import followup
from sdd import review_quality

PROVENANCE = 'grounded-inputs.json'
PREPARED = 'grounded-parent.json'


def install_hooks(original):
    make_native_request = original.make_request
    inspect_native_output = original.inspect_native_output

    def make_request(identity, unit, evidence, candidate=None):
        request = make_native_request(identity, unit, evidence, candidate)
        if candidate is None:
            return request
        prompt = review_quality.KOREAN_REVIEW_INSTRUCTIONS.encode('utf-8') + b'\n' + request['prompt']
        key_data = dict(request['record']['key_data'], prompt_sha256=original.sha256(prompt))
        return dict(request, prompt=prompt, korean_candidate=candidate.decode('utf-8'),
                    record=dict(key_data=key_data, key=original.sha256(original.json_bytes(key_data))))

    def inspect(stdout, output, returncode, request):
        validation, parsed = inspect_native_output(stdout, output, returncode, request)
        if parsed is not None and not validation['issues'] and 'korean_candidate' in request:
            try:
                review_quality.validate_korean_review(original.parse_json(output), request['korean_candidate'])
            except ValueError as error:
                issue = f'korean_review_quality: {error}'
                return dict(validation, issues=sorted({*validation['issues'], issue})), None
        return validation, parsed

    original.make_request = make_request
    original.inspect_native_output = inspect


def policy_identity(original):
    return {name: original.file_sha256(path) for name, path in (
        ('grounded_sha256', Path(__file__)),
        ('followup_sha256', Path(followup.__file__)),
        ('review_quality_sha256', Path(review_quality.__file__)),
    )}


def reject_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f'Symbolic links and reparse points are not allowed here: {path}')


def checked_path(path):
    path = path.absolute()
    for part in (*reversed(path.parents), path):
        reject_link(part)
    return path.resolve()


def check_tree(path):
    reject_link(path)
    for entry in path.rglob('*'):
        reject_link(entry)


def check_disjoint(out, *inputs):
    for source in inputs:
        if source == out or source in out.parents or out in source.parents:
            raise ValueError(f'--out must be disjoint from {source}')


def check_index(original, data):
    index = original.parse_json(data)
    if not isinstance(index, dict) or set(index) != set(original.QUESTIONS):
        raise ValueError('Baseline index does not cover the original questions')
    return index


def checked_draft_attempt(baseline, proof, unit):
    if not isinstance(proof, dict) or not isinstance(proof.get('attempt'), str):
        raise ValueError('Invalid historical draft proof pointer')
    parts = PurePosixPath(proof['attempt']).parts
    if (len(parts) != 5 or parts[:4] != ('baseline', 'attempts', 'draft', unit)
            or parts[4] == '..' or '/' in parts[4] or '\\' in parts[4] or ':' in parts[4]):
        raise ValueError('Historical draft proof points outside its expected unit')
    path = checked_path(baseline.joinpath(*parts))
    check_tree(path)
    return path


def parent_report(original, benchmark):
    phase_attempts = original.phase_attempts

    def fresh_attempts(run, phase):
        attempts = phase_attempts(run, phase)
        if phase == 'baseline':
            return [attempt for attempt in attempts if attempt.get('kind') != 'draft'
                    and '/attempts/draft/' not in '/' + str(attempt.get('attempt', '')).replace('\\', '/')]
        return attempts

    original.phase_attempts = fresh_attempts
    try:
        original.write_report(benchmark)
    finally:
        original.phase_attempts = phase_attempts


def prepare_parent(args, original, policy):
    out, baseline = args.out, args.baseline_run
    draft_digest = followup.INDEXES['candidates.json']
    draft_data = followup.pinned_bytes(checked_path(baseline / 'baseline' / 'candidates.json'), draft_digest)
    drafts = check_index(original, draft_data)
    attempts = {unit: checked_draft_attempt(baseline, proof, unit) for unit, proof in drafts.items()}
    source_run_data = checked_path(baseline / 'run.json').read_bytes()
    source_run = original.parse_json(source_run_data)
    if source_run['script_sha256'] != followup.ORIGINAL:
        raise ValueError('Historical run did not use the pinned original script')
    provenance = dict(policy=policy, baseline=str(baseline), git=str(args.git),
                      script=str(args.original_script), original_sha256=followup.ORIGINAL,
                      commits=[original.PARENT, original.CHILD], candidates_sha256=draft_digest,
                      baseline_run_sha256=original.sha256(source_run_data), execution=source_run['execution'])
    provenance_data = original.json_bytes(provenance)
    marker = out / PROVENANCE
    prepared = out / PREPARED
    assessment_path = out / 'baseline' / 'assessments.json'

    class Parent(original.Benchmark):
        def validate_assessments(self):
            data = assessment_path.read_bytes()
            assessments = check_index(original, data)
            for unit, candidate in self.frozen_candidates().items():
                request = self.request('parent', unit, candidate)
                self.validate_proof(assessments[unit], 'baseline', 'review', unit, request)
            return original.sha256(data)

        def baseline(self):
            if assessment_path.exists():
                self.validate_assessments()
            else:
                super().baseline()

    if args.resume:
        if not marker.is_file() or marker.read_bytes() != provenance_data:
            raise ValueError('Prepared-parent inputs changed or --out was not initialized by this adapter')
    else:
        out.mkdir(parents=True, exist_ok=False)
        original.atomic_write(out / '.gitignore', b'*\n')
    with original.run_lock(out / 'run.lock'):
        original.atomic_write(marker, provenance_data)
        benchmark = Parent(out, original.LocalGit(args.git), original.codex_executable())
        benchmark.record_execution()
        if benchmark.identity != provenance['execution']:
            raise ValueError('Current CLI execution identity differs from the historical draft receipts')
        try:
            benchmark.execute_phase('prepare')
            historical = original.Benchmark(baseline, benchmark.git, benchmark.executable)
            historical.identity = benchmark.identity
            historical.sources = benchmark.get_sources()
            requests = {unit: historical.request('parent', unit) for unit in original.QUESTIONS}
            for unit, request in requests.items():
                historical.validate_proof(drafts[unit], 'baseline', 'draft', unit, request)
            for unit, request in requests.items():
                target = out / drafts[unit]['attempt']
                followup.install_attempt(attempts[unit], target)
                benchmark.validate_proof(drafts[unit], 'baseline', 'draft', unit, request)
            original.atomic_write(out / 'baseline' / 'candidates.json', draft_data)
            if prepared.exists() and not benchmark.phase_done('baseline'):
                raise ValueError('Prepared marker exists without a completed baseline phase')
            benchmark.execute_phase('baseline')
            digest = benchmark.validate_assessments()
        finally:
            parent_report(original, benchmark)
        original.write_json(prepared, dict(provenance_sha256=original.sha256(provenance_data),
                                           assessments_sha256=digest, policy=policy))


def run_arm(args, original, policy):
    baseline = args.baseline_run
    check_tree(baseline)
    marker = original.read_json(baseline / PREPARED)
    provenance_data = (baseline / PROVENANCE).read_bytes()
    provenance = original.parse_json(provenance_data)
    if (marker['policy'] != policy or provenance['policy'] != policy
            or marker['provenance_sha256'] != original.sha256(provenance_data)
            or provenance['original_sha256'] != followup.ORIGINAL
            or provenance['candidates_sha256'] != followup.INDEXES['candidates.json']
            or provenance['git'] != str(args.git)):
        raise ValueError('Prepared parent provenance does not match this benchmark policy and Git input')
    check_disjoint(args.out, checked_path(Path(provenance['baseline'])))
    digest = marker['assessments_sha256']
    followup.pinned_bytes(baseline / 'baseline' / 'assessments.json', digest)
    followup.run(args, original, indexes={'assessments.json': digest}, policy_identity=policy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('original-script', 'baseline-run', 'git', 'out'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--prepare-parent', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--arm', choices=('incremental', 'full'))
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if args.prepare_parent == (args.arm is not None) or args.workers < 1:
        parser.error('Specify either --prepare-parent or --arm and use a positive worker count')
    try:
        for name in ('original_script', 'baseline_run', 'git', 'out'):
            setattr(args, name, checked_path(getattr(args, name)))
        check_disjoint(args.out, args.original_script, args.baseline_run, args.git)
        if not args.baseline_run.is_dir() or not args.git.is_dir():
            raise ValueError('--baseline-run and --git must be existing directories')
        if args.resume:
            check_tree(args.out)
        original = followup.load_original(args.original_script)
    except (OSError, ImportError, ValueError) as error:
        parser.exit(1, f'Cannot initialize grounded benchmark: {error}\n')
    try:
        policy = policy_identity(original)
        install_hooks(original)
        if args.prepare_parent:
            prepare_parent(args, original, policy)
        else:
            run_arm(args, original, policy)
    except KeyboardInterrupt:
        return 130
    except (original.BenchmarkError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f'Grounded benchmark stopped. {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
