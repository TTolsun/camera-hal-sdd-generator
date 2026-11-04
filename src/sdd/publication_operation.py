"""Version a publication contract; retain existing reuse and failure decisions."""
from copy import deepcopy
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .execution_lock import lease
from .state_io import save
from .validation_stage import Inputs, InputChanged


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def directory(cfg):
    operation = cfg.publication.get('operation_id')
    # Short directory names also work below Windows' ordinary path limit.
    # Full identities remain inside records; prefix collisions fail closed.
    return cfg.build_dir/'publication-operations'/hashlib.sha256(operation.encode()).hexdigest()[:16]


def _immutable(path, value):
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError(f'Publication history differs or is damaged: {path}')
    else:
        save(path, value, newline='\n')


def _strings(value, name, *, empty=False):
    if (not isinstance(value, list) or (not value and not empty)
            or any(not isinstance(v, str) or not v.strip() for v in value)
            or len(value) != len(set(value))):
        raise ValueError(f'Publication operation {name} needs unique nonempty strings')


def _validate(contract):
    required = {'schema', 'revision', 'reason', 'sections', 'completion', 'excluded',
                'source_commit', 'profiles', 'prerequisites', 'discoveries'}
    if (not isinstance(contract, dict) or required - contract.keys()
            or set(contract) - required - {'integration', 'change'}
            or contract.get('schema') != 1 or type(contract.get('revision')) is not int
            or contract['revision'] < 1):
        raise ValueError('Invalid publication operation contract schema/revision/fields')
    for key in ('reason', 'source_commit'):
        if not isinstance(contract[key], str) or not contract[key].strip():
            raise ValueError(f'Publication operation requires {key}')
    for key in ('sections', 'completion', 'excluded'):
        _strings(contract[key], key, empty=key == 'excluded')
    if set(contract['sections']) & set(contract['excluded']):
        raise ValueError('Publication target sections also appear in excluded scope')
    profiles = contract['profiles']
    if not isinstance(profiles, dict) or set(profiles) != {'generation', 'translation', 'review'}:
        raise ValueError('Publication operation declares generation/translation/review profiles separately')
    for value in profiles.values():
        if (not isinstance(value, dict) or set(value) != {'kind', 'runner', 'model', 'command', 'args'}
                or any(not isinstance(value[k], str) or not value[k] for k in ('kind', 'runner', 'model'))
                or any(not isinstance(value[k], list) or any(not isinstance(v, str) or not v for v in value[k])
                       for k in ('command', 'args'))):
            raise ValueError('Publication operation profile needs kind/runner/model/command/args')
    if not isinstance(contract['prerequisites'], list) or not isinstance(contract['discoveries'], list):
        raise ValueError('Publication prerequisites and discoveries must be lists')
    if any(not isinstance(r, dict) or r.get('gate') != 'before-generation'
           for r in contract['prerequisites']):
        raise ValueError('Publication prerequisites must run before-generation')
    ids = set()
    for row in contract['discoveries']:
        if (not isinstance(row, dict) or set(row) != {'id', 'kind', 'status', 'reason'}
                or not isinstance(row['id'], str) or not row['id'] or row['id'] in ids
                or row['kind'] not in ('required-defect', 'needs-evidence', 'follow-up')
                or row['status'] not in ('open', 'resolved', 'deferred')
                or not isinstance(row['reason'], str) or not row['reason'].strip()
                or (row['kind'] != 'follow-up' and row['status'] == 'deferred')):
            raise ValueError('Invalid publication discovery classification/disposition')
        ids.add(row['id'])
    if contract['revision'] > 1:
        change = contract.get('change')
        if (not isinstance(change, dict) or set(change) != {'kind', 'reason', 'affected_sections', 'recheck'}
                or change['kind'] not in ('policy', 'input', 'integration', 'user-scope', 'defect')
                or any(not isinstance(change[k], str) or not change[k].strip() for k in ('reason', 'recheck'))):
            raise ValueError('A new publication revision requires change kind/reason/affected_sections/recheck')
        _strings(change['affected_sections'], 'affected_sections', empty=True)


def profile(agent):
    return {k: deepcopy(getattr(agent, k)) for k in ('kind', 'runner', 'model', 'command', 'args')}


def _git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                            encoding='utf-8', check=False)
    if result.returncode:
        raise ValueError('Cannot resolve publication generator integration: ' + result.stderr.strip())
    return result.stdout.strip()


def _source_head(root):
    if not root.is_dir():
        return None
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--is-inside-work-tree'],
            capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'LC_ALL': 'C'})
    except FileNotFoundError:
        if any((p/'.git').exists() for p in (root, *root.parents)):
            raise ValueError('Git is required to verify the configured source checkout') from None
        return None  # An unpacked non-Git source snapshot is still supported.
    if result.returncode:
        if 'not a git repository' in result.stderr.lower():
            return None
        raise ValueError('Cannot identify the publication source checkout: ' + result.stderr.strip())
    if result.stdout.strip() != 'true':
        raise ValueError('Publication source must be a working tree, not a bare Git repository')
    return _git(root, 'rev-parse', '--verify', 'HEAD')


class Contract:
    def __init__(self, execution, phase):
        self.execution, self.cfg, self.watch = execution, execution.cfg, Inputs()
        self.outputs = []
        self.rollbacks = []
        self.sealed_head = None
        self.git_checks = []
        self.output_lease = None
        self.commit_lease = None
        try:
            self._prepare(phase)
        except BaseException:
            self.close()
            raise

    def _prepare(self, phase):
        cfg = self.cfg
        model = self.execution.publication_model
        if model is None and cfg.facts_path.is_file():
            from .facts.model import KnowledgeModel
            model = KnowledgeModel.from_dict(json.loads(self.watch.read(cfg.facts_path)))
        # This operation resolves the selected source HEAD itself. The existing
        # stage/checkpoint guards retain their default Git-file observation.
        self.watch.pin(cfg, model, include_source_git=False)
        self._pin_publication_inputs()
        # Execution can temporarily lower the transport timeout to an explicit
        # existing budget. Input files and the declared CLI identity stay fixed.
        self.watch.objects.pop(id(cfg), None)
        self.configuration = self._configuration()
        path = cfg.root/cfg.publication['operation_file']
        self.contract = json.loads(self.watch.read(path))
        _validate(self.contract)
        self.contract_sha256 = checksum(self.contract)
        self.execution.report['publication_attempt'] = dict(
            revision=self.contract['revision'], contract_sha256=self.contract_sha256, path=str(path),
            contract=deepcopy(self.contract))
        if model is not None:
            self.check_source(model.meta.get('source_commit'))
        source_head = _source_head(cfg.source_root)
        if source_head is not None:
            self.check_source(source_head)
            if model is not None:
                prefix = _git(cfg.source_root, 'rev-parse', '--show-prefix')
                selected = {prefix+r['file'] for r in model.evidence.values()
                            if r.get('file') and not r['file'].startswith('@') and r.get('kind') != 'product'}
                tracked = set(_git(cfg.source_root, 'ls-files', '--full-name', '-z').split('\0'))
                changed = set(_git(cfg.source_root, 'diff', '--name-only', '--no-renames', '-z',
                                   'HEAD', '--', '.').split('\0'))
                if selected - tracked or selected & changed:
                    raise ValueError('Publication evidence files differ from the declared committed source')
            self.git_checks.append((cfg.source_root, 'HEAD', source_head))
        self.role = {'generation': 'generation', 'translation': 'translation',
                     'contract-audit': 'review'}.get(phase)
        if self.role and profile(cfg.agent) != self.contract['profiles'][self.role]:
            raise ValueError(f'Publication operation {self.role} CLI differs from its declared profile')
        from .publication_reports import check_reports
        check_reports(cfg, 'before-generation', reports=self.contract['prerequisites'])
        # Pin prerequisite bytes as well as the operation file before the first
        # call. A passing historical report cannot be replaced mid-execution.
        for report in self.contract['prerequisites']:
            if hashlib.sha256(self.watch.read(cfg.root/report['path'])).hexdigest() != report['sha256']:
                raise ValueError('Publication prerequisite changed after validation')
        facts = json.loads(self.watch.read(cfg.facts_path)) if cfg.facts_path.is_file() else None
        if facts is not None:
            self.check_source(facts.get('meta', {}).get('source_commit'))
        generator = Path(__file__).resolve().parents[2]
        integration = self.contract.get('integration')
        resolved = None
        if integration is not None:
            if (not isinstance(integration, dict) or set(integration) != {'root', 'ref', 'commit'}
                    or any(not isinstance(v, str) or not v for v in integration.values())
                    or not integration['ref'].startswith('refs/')):
                raise ValueError('Publication integration requires root/ref/commit')
            integration_root = (cfg.root/integration['root']).resolve()
            resolved = _git(integration_root, 'rev-parse', '--verify', integration['ref']+'^{commit}')
            if resolved != integration['commit']:
                raise ValueError('Publication integration ref changed; integrate/verify and record a new revision')
            self.git_checks.append((integration_root, integration['ref'], resolved))
        generator_commit = None
        if (generator/'.git').exists():
            generator_commit = _git(generator, 'rev-parse', '--verify', 'HEAD')
            self.git_checks.append((generator, 'HEAD', generator_commit))
        # Content fingerprints work in installed/offline environments too; Git
        # hosting and an origin/main convention are not mandatory dependencies.
        basis = dict(configuration={k: v for k, v in cfg.raw.items() if k != 'publication'},
                     source_commit=self.contract['source_commit'], source_head=source_head,
                     generator_commit=generator_commit,
                     integration_commit=resolved,
                     sections=cfg.sections(), scenarios=cfg.scenarios(),
                     inputs=self.watch.manifest())
        # Produced prerequisite reports and the editable contract are bound
        # separately. Their update need not masquerade as a source/policy edit.
        for p in [path, *[cfg.root/r['path'] for r in self.contract['prerequisites']]]:
            basis['inputs'].pop(str(p.resolve()), None)
        self.basis_sha256 = checksum(basis)
        payload = deepcopy(dict(operation_id=self.execution.operation, contract=self.contract,
                       contract_sha256=self.contract_sha256, basis=basis,
                       basis_sha256=self.basis_sha256))
        base = directory(cfg)
        with lease(cfg, 'publication-history-'+base.name):
            _immutable(base/'identity.json', dict(operation_id=self.execution.operation))
            self.watch.read(base/'identity.json')
            runs = self.execution.prior()
            # A write-ahead record in the existing execution journal closes
            # the crash window between preserving a revision and its head.
            # Recover exactly that intent, never a replacement/new judgement.
            for run in runs:
                intent = run.get('publication_revision')
                if intent is not None:
                    if (intent.get('sha256') != checksum(intent.get('payload'))
                            or intent['payload'].get('operation_id') != self.execution.operation):
                        raise ValueError('Publication revision intent is damaged')
                    number = intent['payload']['contract']['revision']
                    if type(number) is not int or number < 1:
                        raise ValueError('Publication revision intent has an invalid revision')
                    _immutable(base/'revisions'/f'{number:06d}.json', intent)
            prior = []
            for index, old in enumerate(sorted((base/'revisions').glob('*.json')), 1):
                saved = json.loads(self.watch.read(old))
                if (saved.get('sha256') != checksum(saved.get('payload'))
                        or saved['payload'].get('operation_id') != self.execution.operation
                        or saved['payload']['contract']['revision'] != index
                        or old.name != f'{index:06d}.json'
                        or saved['payload'].get('previous_sha256') != (prior[-1]['sha256'] if prior else None)):
                    raise ValueError('Publication revision history is damaged')
                prior.append(saved)
            # The head survives removal of a history suffix. Completed run
            # bindings also reject deletion of both that suffix and its head.
            head = base/'head.json'
            anchors = [dict(revision=r['payload']['contract']['revision'], sha256=r['sha256']) for r in prior]
            if head.exists():
                sealed = json.loads(head.read_bytes())
                if sealed not in anchors[-2:]:
                    raise ValueError('Publication history head is missing or changed')
            for run in runs:
                bound = run.get('publication')
                if bound:
                    saved = next((p['payload'] for p in prior
                                  if p['payload']['contract']['revision'] == bound['revision']), None)
                    if (saved is None or saved['basis_sha256'] != bound['basis_sha256']
                            or saved['contract_sha256'] != bound['contract_sha256']):
                        raise ValueError('Publication history no longer matches an existing execution')
                for planned in run.get('publication_plans', []):
                    original = base/'plans'/(planned['input_sha256'][:16]+'.json')
                    try:
                        record = json.loads(self.watch.read(original))
                    except (OSError, ValueError) as exc:
                        raise ValueError('Publication plan history is missing or damaged') from exc
                    if (record.get('operation_id') != self.execution.operation
                            or record.get('input_sha256') != planned['input_sha256']
                            or checksum({k: v for k, v in record.items() if k != 'input_sha256'}) != planned['input_sha256']):
                        raise ValueError('Publication plan history no longer matches an existing execution')
            revision = self.contract['revision']
            previous = prior[:-1] if prior and revision == prior[-1]['payload']['contract']['revision'] else prior
            payload['previous_sha256'] = previous[-1]['sha256'] if previous else None
            if prior and revision == prior[-1]['payload']['contract']['revision']:
                if payload != prior[-1]['payload']:
                    raise ValueError('Publication inputs or contract changed; record a new revision and recheck reason')
            elif revision != (prior[-1]['payload']['contract']['revision']+1 if prior else 1):
                raise ValueError('Publication revisions must extend the preserved history in order')
            self.reference = dict(operation_id=self.execution.operation, revision=revision,
                                  contract_sha256=self.contract_sha256, basis_sha256=self.basis_sha256)
            self.reference['path'] = str(base/'revisions'/f'{revision:06d}.json')
            self.verify()
            digest = checksum(payload)
            intent = dict(payload=payload, sha256=digest)
            self.execution.report['publication_revision'] = intent
            self.execution.persist()
            _immutable(Path(self.reference['path']), intent)
            if json.loads(self.watch.read(Path(self.reference['path']))) != dict(payload=payload, sha256=digest):
                raise InputChanged('Publication revision changed while being preserved')
            save(head, dict(revision=revision, sha256=digest), newline='\n')
            self.sealed_head = (head, dict(revision=revision, sha256=digest))
        self.execution.report['publication'] = self.reference

    def check_source(self, commit):
        if commit != self.contract['source_commit']:
            raise ValueError('Publication source commit differs from the operation contract')

    def _pin_publication_inputs(self):
        from .product_context import input_paths
        from .render_profiles import paths, for_page
        for path in input_paths(self.cfg):
            self.watch.read(path)
        for name in (self.cfg.visuals.file, self.cfg.site.intro, self.cfg.site.guide_visuals):
            if name:
                self.watch.read(self.cfg.root/name)
        directories = [(Path(__file__).parent/'site_assets', '*')]
        for page, path in paths(self.cfg).items():
            self.watch.read(path)
            directories.append((for_page(self.cfg, page).style_dir, '*.md'))
        for directory, pattern in directories:
            files = tuple(sorted(p for p in directory.rglob(pattern) if p.is_file()))
            self.watch.directories[(directory, pattern)] = files
            for path in files:
                self.watch.read(path)

    def select(self, model, sections):
        self.check_source(model.meta.get('source_commit'))
        if set(sections) - set(self.contract['sections']):
            raise ValueError('Publication selection exceeds operation scope; record the scope change first')

    def verify(self):
        self.watch.verify()
        # Resolve selected refs, not the shared packed-refs file: packing an
        # unrelated parallel branch does not change this publication's basis.
        for root, ref, expected in self.git_checks:
            if _git(root, 'rev-parse', '--verify', ref+'^{commit}') != expected:
                raise InputChanged('Publication generator or integration ref changed; record a new basis')
        if self._configuration() != self.configuration or checksum(self.contract) != self.contract_sha256:
            raise InputChanged('Publication in-memory configuration or contract changed; previous output preserved')
        if self.sealed_head:
            path, expected = self.sealed_head
            if not path.is_file() or json.loads(path.read_bytes()) != expected:
                raise InputChanged('Publication operation was superseded; replan before continuing')
        if self.role and profile(self.cfg.agent) != self.contract['profiles'][self.role]:
            raise ValueError('Publication CLI identity changed during execution')

    def _configuration(self):
        value = asdict(self.cfg)
        value['agent'].pop('timeout_sec', None)
        return value

    def enter_phase(self, name):
        previous = self.role
        role = {'generation': 'generation', 'translation': 'translation', 'contract-audit': 'review'}.get(name)
        if role:
            if profile(self.cfg.agent) != self.contract['profiles'][role]:
                raise ValueError(f'Publication operation {role} CLI differs from its declared profile')
            self.role = role
        return previous

    def verify_transport(self, transport):
        from .config import AgentConfig
        if self.role is None:
            raise ValueError('Publication model call requires a declared execution phase')
        expected = self.contract['profiles'][self.role]
        actual = getattr(getattr(transport, '__self__', None), 'cfg', None)
        if not isinstance(actual, AgentConfig) or profile(actual) != expected:
            raise ValueError('Actual publication transport differs from the declared CLI profile')

    def final_gate(self):
        from .config import section_output
        configured = {s['id']: s for s in self.cfg.sections()}
        missing = [sid for sid in self.contract['sections']
                   if sid not in configured or not (self.cfg.sdd_dir/section_output(configured[sid])).is_file()]
        if missing:
            raise ValueError('Publication required documents remain incomplete: ' + ', '.join(missing))
        pending = [r['id'] for r in self.contract['discoveries']
                   if r['kind'] != 'follow-up' and r['status'] != 'resolved']
        if pending:
            raise ValueError('Publication required findings remain unresolved: ' + ', '.join(pending))

    def preserve_output(self, path, text):
        self.begin_output()
        self.outputs.append((path, path.read_bytes() if path.exists() else None,
                             (text.rstrip()+'\n').encode('utf-8')))

    def rollback(self):
        for undo in reversed(self.rollbacks):
            undo()
        for path, previous, produced in reversed(self.outputs):
            if not path.is_file() or path.read_bytes() != produced:
                self.execution.report.setdefault('rollback_conflicts', []).append(str(path))
            elif previous is None:
                path.unlink()
            else:
                path.write_bytes(previous)

    def begin_output(self):
        """Serialize this operation's commit/rollback with revision adoption."""
        if self.commit_lease is None:
            # Only the output transaction is serialized across operations in
            # this workspace. Source review and native CLI work stay concurrent.
            guard = lease(self.cfg, 'publication-output-commit')
            guard.__enter__()
            self.commit_lease = guard
        if self.output_lease is None:
            guard = lease(self.cfg, 'publication-history-'+directory(self.cfg).name)
            guard.__enter__()
            self.output_lease = guard
        self.verify()

    def close(self, error=None):
        try:
            if self.output_lease is not None:
                self.output_lease.__exit__(type(error) if error else None, error,
                                           error.__traceback__ if error else None)
                self.output_lease = None
        finally:
            try:
                if self.commit_lease is not None:
                    self.commit_lease.__exit__(type(error) if error else None, error,
                                               error.__traceback__ if error else None)
                    self.commit_lease = None
            finally:
                self.watch.changes.close()


def archive_plan(cfg, report, execution=None):
    """Immutable plan snapshots; the legacy filename remains the latest view."""
    contract = getattr(execution, 'publication_contract', None) if execution else None
    if contract:
        report['publication'] = contract.reference
    report['operation_id'] = cfg.publication.get('operation_id')
    report['input_sha256'] = checksum({k: v for k, v in report.items() if k != 'input_sha256'})
    if report['operation_id']:
        base = directory(cfg)
        path = base/'plans'/(report['input_sha256'][:16]+'.json')
        with (nullcontext() if contract and contract.output_lease is not None
              else lease(cfg, 'publication-history-'+base.name)):
            _immutable(base/'identity.json', dict(operation_id=report['operation_id']))
            _immutable(path, report)
            if contract and json.loads(contract.watch.read(path)) != report:
                raise InputChanged('Publication plan changed while being preserved')
        if execution:
            execution.report.setdefault('publication_plans', []).append(dict(
                path=str(path), input_sha256=report['input_sha256']))
            execution.persist()
    # Preserve the pre-adoption latest view too. Older plans do not contain an
    # operation_id, so retain exact bytes without inventing an association.
    latest = cfg.build_dir/'publication-plan.json'
    with lease(cfg, 'publication-plan-view'):
        if latest.exists():
            previous = latest.read_bytes()
            digest = hashlib.sha256(previous).hexdigest()
            preserved = cfg.build_dir/'publication-operations'/'prior-views'/(digest[:16]+'.json')
            _immutable(preserved, dict(schema=1, original_sha256=digest,
                association='Unattributed latest view; original bytes retained, no new validation',
                original_json_utf8=previous.decode('utf-8')))
            if latest.read_bytes() != previous:
                raise InputChanged('Latest publication plan changed while being preserved')
        save(latest, report, newline='\n')
