"""Operation boundaries on real entry points; transports are explicit doubles."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import os
import shutil

import pytest

from test_generated_design import generated, cli_units
from sdd.generate import Generator
from sdd.generation_run import Execution
from sdd.publication_operation import directory, profile
from sdd.validation_stage import InputChanged


@pytest.fixture(autouse=True)
def isolate_synthetic_source_from_the_generator_repository(tmp_cfg, monkeypatch):
    # The synthetic hal/ directory is not a checkout of this generator. Real
    # source repositories created below remain discoverable above their subdirs.
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_cfg.root))


def configure(cfg, model, sections):
    cfg.raw['publication'] = dict(operation_id='one-publication', operation_file='operation.json')
    declaration = dict(schema=1, revision=1, reason='Complete the fixed reader task.',
        sections=sections, completion=['Generate and verify the selected answers.'],
        excluded=['Unrelated reader improvements.'], source_commit=model.meta['source_commit'],
        profiles={role: profile(cfg.agent) for role in ('generation', 'translation', 'review')},
        prerequisites=[], discoveries=[])
    def write():
        (cfg.root/'operation.json').write_text(json.dumps(declaration), encoding='utf-8')
    write()
    return declaration, write


def revisions(cfg):
    return sorted((directory(cfg)/'revisions').glob('*.json'))


def bump(contract, *, kind='input', affected=None):
    contract['revision'] += 1
    contract['change'] = dict(kind=kind, reason='Apply the explicit changed publication basis.',
                             affected_sections=affected or [], recheck='Run existing checks on the changed targets.')


def test_resume_links_immutable_plans_to_runs_and_preserves_original_output(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    target = tmp_cfg.sdd_dir/'device.md'
    target.parent.mkdir(parents=True)
    target.write_text('old published output', encoding='utf-8')
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run()
    assert target.read_text(encoding='utf-8') == 'old published output'
    old = {p: p.read_bytes() for p in (directory(tmp_cfg)/'plans').glob('*.json')}
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'prepare']
    assert all(p.read_bytes() == raw for p, raw in old.items())
    assert len(revisions(tmp_cfg)) == 1
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert len(runs) == 2
    for run in runs:
        assert run['publication']['revision'] == 1
        assert run['publication_plans']
        assert all(Path(p['path']).exists() for p in run['publication_plans'])


def test_pending_prerequisite_blocks_all_calls_then_allows_first_execution(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    payload = dict(status='passed', policy='integrated-and-tested')
    raw = json.dumps(payload).encode()
    contract['prerequisites'] = [dict(path='policy-test.json', gate='before-generation',
        producer='policy-tests', sha256=hashlib.sha256(raw).hexdigest(), bindings=payload)]
    write()
    with pytest.raises(FileNotFoundError):
        Generator(tmp_cfg, model, agent()).run()
    assert not calls and not revisions(tmp_cfg)
    failed = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert failed[0]['publication_attempt']['contract'] == contract
    (tmp_cfg.root/'policy-test.json').write_bytes(raw)
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare']


def test_changed_basis_requires_reasoned_revision_and_keeps_old_history(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    old_revision = revisions(tmp_cfg)[0].read_bytes()
    completed = list(calls)
    section['design_topics'][0]['question'] += ' 정지 책임도 확인하세요.'
    save()
    with pytest.raises(ValueError, match='new revision'):
        Generator(tmp_cfg, model, agent()).run()
    assert calls == completed
    bump(contract, affected=[section['id']]); write()
    Generator(tmp_cfg, model, agent()).run()
    assert calls == completed+['stop']
    assert len(revisions(tmp_cfg)) == 2
    assert revisions(tmp_cfg)[0].read_bytes() == old_revision


def test_user_scope_addition_is_explicit_and_followup_does_not_expand_it(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, ['different-document'])
    contract['discoveries'] = [dict(id='other-improvement', kind='follow-up', status='deferred',
                                   reason='Outside the fixed reader task; retain for follow-up.')]
    write()
    with pytest.raises(ValueError, match='exceeds operation scope'):
        Generator(tmp_cfg, model, agent()).run()
    assert not calls
    contract['sections'].append(section['id'])
    bump(contract, kind='user-scope', affected=[section['id']]); write()
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare']
    assert json.loads(revisions(tmp_cfg)[-1].read_bytes())['payload']['contract']['discoveries']


def test_input_edit_during_call_fails_before_any_manuscript_replacement(cli_units, tmp_cfg, monkeypatch):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    target = tmp_cfg.sdd_dir/'device.md'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'old output')
    import sdd.cli_agent as cli
    original = cli.run
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        contract['reason'] = 'Changed during the live call.'
        write()
        return result
    monkeypatch.setattr(cli, 'run', mutate)
    with pytest.raises(ValueError, match='changed'):
        Generator(tmp_cfg, model, agent()).run()
    assert target.read_bytes() == b'old output'
    assert len(calls) == 1


def test_integration_ref_change_is_detected_without_modifying_parallel_repository(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    git = tmp_cfg.root/'isolated-generator'
    git.mkdir()
    def command(*args):
        return subprocess.run(['git', '-C', str(git), *args], check=True, capture_output=True,
                              text=True, encoding='utf-8').stdout.strip()
    command('init')
    command('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'baseline')
    first = command('rev-parse', 'HEAD')
    command('update-ref', 'refs/heads/integration', first)
    contract['integration'] = dict(root=str(git), ref='refs/heads/integration', commit=first)
    write()
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    old = list(calls)
    execution = Execution(tmp_cfg, object(), model=model)
    with execution.track('generation'):
        command('branch', 'unrelated-parallel-work')
        command('pack-refs', '--all')
        execution.publication_contract.verify()  # Selected commits did not change.
    command('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'parallel policy')
    second = command('rev-parse', 'HEAD')
    command('update-ref', 'refs/heads/integration', second)
    with pytest.raises(ValueError, match='integration ref changed'):
        Generator(tmp_cfg, model, agent()).run()
    assert calls == old
    contract['integration']['commit'] = second
    bump(contract, kind='integration', affected=[section['id']]); write()
    Generator(tmp_cfg, model, agent()).run()
    assert calls == old  # Existing validators retain their own reuse decision.
    assert len(revisions(tmp_cfg)) == 2


def test_required_findings_block_export_but_not_repair_and_profile_is_separate(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    contract['discoveries'] = [dict(id='mandatory-condition', kind='required-defect', status='open',
                                   reason='Repair the condition before publication.')]
    write()
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    with pytest.raises(ValueError, match='unresolved'):
        with Execution(tmp_cfg, object()).track('export_site'):
            pytest.fail('must not export')
    tmp_cfg.agent.model = 'other-review-model'
    with pytest.raises(ValueError, match='review CLI'):
        with Execution(tmp_cfg, object()).track('contract-audit'):
            pytest.fail('must not call review')
    tmp_cfg.agent.model = contract['profiles']['review']['model']
    bump(contract, kind='defect', affected=[section['id']])
    contract['discoveries'][0]['status'] = 'resolved'; write()
    with Execution(tmp_cfg, object()).track('export_site'):
        pass


def test_operation_id_without_contract_still_preserves_plan_history(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    tmp_cfg.raw['publication'] = dict(operation_id='legacy-task')
    legacy = b'{"schema": 1, "original": "unattributed pre-adoption plan"}\r\n'
    tmp_cfg.build_dir.mkdir(parents=True, exist_ok=True)
    (tmp_cfg.build_dir/'publication-plan.json').write_bytes(legacy)
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    old = {p: p.read_bytes() for p in (directory(tmp_cfg)/'plans').glob('*.json')}
    Generator(tmp_cfg, model, agent()).run()
    assert old and all(p.read_bytes() == raw for p, raw in old.items())
    preserved = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'publication-operations/prior-views').glob('*.json')]
    assert any(row['original_json_utf8'].encode() == legacy for row in preserved)


@pytest.mark.parametrize('remove_head', [False, True])
def test_deleted_history_suffix_is_not_recreated(tmp_cfg, sample_model, remove_head):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    with Execution(tmp_cfg, object()).track('generation'):
        pass
    bump(contract); write()
    with Execution(tmp_cfg, object()).track('generation'):
        pass
    original = revisions(tmp_cfg)[-1].read_bytes()
    revisions(tmp_cfg)[-1].unlink()
    if remove_head:
        (directory(tmp_cfg)/'head.json').unlink()
    contract['reason'] = 'A replacement must not erase the deleted version.'; write()
    with pytest.raises(ValueError, match='history|new revision'):
        with Execution(tmp_cfg, object()).track('generation'):
            pytest.fail('deleted history was accepted')
    assert len(revisions(tmp_cfg)) == 2
    assert revisions(tmp_cfg)[-1].read_bytes() == original


def test_uncommitted_running_package_code_is_pinned(tmp_cfg, sample_model):
    """Mutate a private installed package copy, never the shared test source."""
    from sdd import publication_operation
    isolated = tmp_cfg.root/'private'
    shutil.copytree(Path(publication_operation.__file__).parent, isolated/'sdd',
                    ignore=shutil.ignore_patterns('__pycache__'))
    script = '''
from pathlib import Path
import json
from sdd.config import load
from sdd.generation_run import Execution
from sdd.publication_operation import profile, directory
from sdd.validation_stage import InputChanged
cfg = load(Path('sdd.yaml').resolve())
cfg.raw['publication'] = dict(operation_id='package-code', operation_file='operation.json')
contract = dict(schema=1, revision=1, reason='Fixed task.', sections=['device'],
 completion=['Verify the fixed task.'], excluded=[], source_commit='abc123',
 profiles={k: profile(cfg.agent) for k in ('generation','translation','review')},
 prerequisites=[], discoveries=[])
def write():
 Path('operation.json').write_text(json.dumps(contract), encoding='utf-8')
write()
with Execution(cfg, object()).track('generation'):
 pass
saved = json.loads(next((directory(cfg)/'revisions').glob('*.json')).read_bytes())
target = Path(__import__('sdd.grounding', fromlist=['']).__file__)
assert str(target.resolve()) in saved['payload']['basis']['inputs']
target.write_bytes(target.read_bytes()+b'\\n# changed without a Git commit\\n')
try:
 with Execution(cfg, object()).track('generation'):
  raise AssertionError('stale basis accepted')
except ValueError as exc:
 assert 'new revision' in str(exc), str(exc)
contract['revision'] = 2
contract['change'] = dict(kind='policy', reason='Apply the new code.', affected_sections=['device'], recheck='Verify current policy.')
write()
try:
 with Execution(cfg, object()).track('generation'):
  target.write_bytes(target.read_bytes()+b'\\n# changed during execution\\n')
except InputChanged:
 pass
else:
 raise AssertionError('live code edit accepted')
print('private package code pinned before and during execution')
'''
    result = subprocess.run([__import__('sys').executable, '-c', script], cwd=tmp_cfg.root,
        env={**os.environ, 'PYTHONPATH': str(isolated), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout+result.stderr


def test_contract_edit_after_write_rolls_back_only_owned_manuscript(cli_units, tmp_cfg, monkeypatch):
    section, model, save, calls, state, agent = cli_units
    contract, write = configure(tmp_cfg, model, [section['id']])
    target = tmp_cfg.sdd_dir/'device.md'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'previous manuscript')
    from sdd.page_writer import PageWriter
    original = PageWriter._write
    def edit_after_write(path, text):
        result = original(path, text)
        contract['reason'] = 'Changed while replacing the output.'; write()
        return result
    monkeypatch.setattr(PageWriter, '_write', staticmethod(edit_after_write))
    state['interrupt'] = False
    with pytest.raises(InputChanged):
        Generator(tmp_cfg, model, agent()).run()
    assert target.read_bytes() == b'previous manuscript'


@pytest.mark.parametrize('phase,role', [('translation', 'translation'), ('contract-audit', 'review')])
def test_nested_phase_cannot_bypass_declared_cli_profile(tmp_cfg, sample_model, phase, role):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    contract['profiles'][role]['model'] = 'independent-selected-model'; write()
    execution = Execution(tmp_cfg, object())
    with execution.track('generation'):
        with pytest.raises(ValueError, match=role+' CLI'):
            with execution.phase(phase):
                pytest.fail('wrong nested CLI profile accepted')
        assert execution.publication_contract.role == 'generation'


def test_new_contract_revision_supersedes_an_active_older_execution(tmp_cfg, sample_model):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    newer = deepcopy(tmp_cfg)
    newer.raw['publication']['operation_file'] = 'operation-new.json'
    updated = deepcopy(contract)
    bump(updated, kind='user-scope', affected=['device'])
    (tmp_cfg.root/'operation-new.json').write_text(json.dumps(updated), encoding='utf-8')
    class Agent:
        def chat(self, *args, **kwargs):
            pytest.fail('superseded operation must not call the CLI')
    old = Execution(tmp_cfg, Agent())
    with pytest.raises(InputChanged, match='superseded'):
        with old.track('generation'):
            with Execution(newer, object()).track('generation'):
                pass
            old.chat('system', 'user')
    assert not old.report['calls']
    assert len(revisions(tmp_cfg)) == 2


def test_final_operation_check_retains_the_existing_site_rollback(tmp_cfg, sample_model, monkeypatch):
    """The site's existing transaction remains live through phase acceptance."""
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    section = tmp_cfg.sections()[0]
    contract['sections'] = [section['id']]; write()
    from sdd.config import section_output
    document = tmp_cfg.sdd_dir/section_output(section)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text('Existing document; normal exporter checks are separate.', encoding='utf-8')
    from sdd.validation_execution import staged
    from sdd.validation_stage import current
    site = tmp_cfg.root/'published.html'
    site.write_bytes(b'previous site')
    @staged
    def export_site(cfg):
        current().rollbacks.append(lambda: site.write_bytes(b'previous site'))
        site.write_bytes(b'new site')
        return site
    # Simulate an edit after the inner input stage accepted the site. Its
    # rollback must still be available to the outer operation's final check.
    import sdd.publication_operation as operations
    original = operations.Contract.verify
    def edit_after_inner_check(self):
        original(self)
        if site.read_bytes() == b'new site' and not getattr(self, '_changed', False):
            self._changed = True
            contract['reason'] = 'Changed after the inner site transaction.'; write()
    monkeypatch.setattr(operations.Contract, 'verify', edit_after_inner_check)
    with pytest.raises(InputChanged):
        export_site(tmp_cfg)
    assert site.read_bytes() == b'previous site'


def test_missing_declared_document_blocks_the_actual_export_entry(tmp_cfg, sample_model):
    contract, write = configure(tmp_cfg, sample_model, ['not-in-effective-profile'])
    from sdd.export_site import export_site
    with pytest.raises(ValueError, match='documents remain incomplete'):
        export_site(tmp_cfg)
    assert not (tmp_cfg.build_dir/'site').exists()


def test_model_source_files_are_bound_through_the_whole_operation(tmp_cfg, sample_model):
    source = tmp_cfg.source_root/'camera.cpp'
    source.write_text('void stop() {}', encoding='utf-8')
    sample_model.evidence['example'] = dict(file='camera.cpp', text='void stop() {}')
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    with pytest.raises(InputChanged):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            source.write_text('void stop() { changed(); }', encoding='utf-8')
    saved = json.loads(revisions(tmp_cfg)[0].read_bytes())
    assert str(source.resolve()) in saved['payload']['basis']['inputs']
    with pytest.raises(ValueError, match='new revision'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('edited source accepted under the old operation revision')


def test_actual_supplied_cli_transport_must_match_declared_profile(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    configure(tmp_cfg, model, [section['id']])
    from sdd.llm import Agent
    different = deepcopy(tmp_cfg.agent)
    different.model = 'undeclared-model'
    execution = Execution(tmp_cfg, Agent(different, tmp_cfg.build_dir/'different-prompts'), model=model)
    with pytest.raises(ValueError, match='Actual publication transport'):
        with execution.track('generation'):
            execution.chat('system', 'user')
    assert not calls and not execution.report['calls']


def test_new_operation_revision_still_uses_actual_export_stale_source_checks(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    model.save(tmp_cfg.facts_path)
    contract, write = configure(tmp_cfg, model, [section['id']])
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    raw = path.read_text(encoding='utf-8')
    path.write_text(raw.replace('source_commit: '+model.meta['source_commit'], 'source_commit: stale-source'), encoding='utf-8')
    bump(contract); write()
    site = tmp_cfg.build_dir/'site'
    site.mkdir()
    old = site/'old.html'
    old.write_bytes(b'published site')
    from sdd.export_site import export_site
    with pytest.raises((RuntimeError, ValueError), match='commit|source|근거'):
        export_site(tmp_cfg, out=site)
    assert old.read_bytes() == b'published site'


def test_in_memory_setting_changes_are_guarded_but_budget_timeout_is_transient(tmp_cfg, sample_model):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    execution = Execution(tmp_cfg, object(), model=sample_model)
    with execution.track('generation'):
        timeout = tmp_cfg.agent.timeout_sec
        tmp_cfg.agent.timeout_sec = timeout/2
        execution.publication_contract.verify()
        tmp_cfg.agent.timeout_sec = timeout
    failed = Execution(tmp_cfg, object(), model=sample_model)
    with pytest.raises(InputChanged, match='in-memory'):
        with failed.track('generation'):
            tmp_cfg.raw['review']['max_retries'] += 1
    from sdd.publication_operation import checksum
    intent = failed.report['publication_revision']
    assert intent['sha256'] == checksum(intent['payload'])
    bump(contract, kind='policy'); write()
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass


def test_explicit_section_exclusion_cannot_overlap_the_targets(tmp_cfg, sample_model):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    contract['excluded'].append('device'); write()
    with pytest.raises(ValueError, match='excluded scope'):
        with Execution(tmp_cfg, object()).track('generation'):
            pytest.fail('explicit exclusion ignored')


@pytest.mark.parametrize('target', ['revision', 'plan'])
def test_live_immutable_history_damage_is_detected(tmp_cfg, sample_model, target):
    configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    execution = Execution(tmp_cfg, object(), model=sample_model)
    with pytest.raises(InputChanged):
        with execution.track('generation'):
            if target == 'revision':
                revisions(tmp_cfg)[0].unlink()
            else:
                from sdd.publication_operation import archive_plan
                report = dict(schema=1, source_commit=sample_model.meta['source_commit'], units=[])
                archive_plan(tmp_cfg, report, execution)
                Path(execution.report['publication_plans'][-1]['path']).unlink()


def test_mismatched_source_checkout_is_rejected_before_any_call(tmp_cfg, sample_model):
    configure(tmp_cfg, sample_model, ['device'])
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_cfg.source_root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','other-source')
    with pytest.raises(ValueError, match='source commit differs'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('mixed source checkout accepted')


def test_missing_previous_plan_is_not_silently_forgotten(tmp_cfg, sample_model):
    configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    from sdd.publication_operation import archive_plan
    execution = Execution(tmp_cfg, object(), model=sample_model)
    with execution.track('generation'):
        archive_plan(tmp_cfg, dict(schema=1, units=[]), execution)
    Path(execution.report['publication_plans'][0]['path']).unlink()
    with pytest.raises(ValueError, match='plan history'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('missing previous plan accepted')


def test_revision_intent_recovers_a_crash_before_snapshot_write(tmp_cfg, sample_model, monkeypatch):
    configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    import sdd.publication_operation as operations
    original = operations._immutable
    def crash(path, value):
        if path.parent.name == 'revisions':
            raise RuntimeError('interrupted before revision snapshot')
        return original(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(operations, '_immutable', crash)
        with pytest.raises(RuntimeError, match='interrupted before revision'):
            with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
                pytest.fail('crash injection not reached')
    assert not revisions(tmp_cfg)
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass
    assert len(revisions(tmp_cfg)) == 1


def test_source_ref_packing_does_not_change_operation_basis(tmp_cfg, sample_model):
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_cfg.source_root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','source')
    sample_model.meta['source_commit'] = git('rev-parse','HEAD')
    configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    execution = Execution(tmp_cfg, object(), model=sample_model)
    with execution.track('generation'):
        git('branch', 'unrelated')
        git('pack-refs', '--all')
        execution.publication_contract.verify()


def test_source_root_below_repository_root_is_not_a_commit_check_bypass(tmp_cfg, sample_model):
    upstream = tmp_cfg.root/'upstream'
    upstream.mkdir()
    module = upstream/'hal'
    module.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(upstream), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','source')
    tmp_cfg.source_root = module
    contract, write = configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    with pytest.raises(ValueError, match='source commit differs'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('mismatched ancestor checkout accepted')
    contract['source_commit'] = sample_model.meta['source_commit'] = git('rev-parse','HEAD')
    write()
    with pytest.raises(InputChanged, match='ref changed'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-m','changed source')


def test_progress_is_visible_before_operation_preparation(tmp_cfg, sample_model, monkeypatch):
    configure(tmp_cfg, sample_model, [tmp_cfg.sections()[0]['id']])
    import sdd.publication_operation as operations
    original = operations.Contract
    def inspect_progress(execution, phase):
        saved = json.loads(execution.path.read_bytes())
        assert saved['current_phase'] == 'generation'
        assert saved['phases'][-1]['status'] == 'running'
        return original(execution, phase)
    monkeypatch.setattr(operations, 'Contract', inspect_progress)
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass


def test_revision_adoption_cannot_cross_output_commit(tmp_cfg, sample_model):
    from sdd.execution_lock import AlreadyRunning
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    newer = deepcopy(tmp_cfg)
    newer.raw['publication']['operation_file'] = 'next-operation.json'
    updated = deepcopy(contract)
    bump(updated, kind='user-scope', affected=['device'])
    (tmp_cfg.root/'next-operation.json').write_text(json.dumps(updated), encoding='utf-8')
    execution = Execution(tmp_cfg, object(), model=sample_model)
    with execution.track('generation'):
        execution.publication_contract.begin_output()
        with pytest.raises(AlreadyRunning):
            with Execution(newer, object(), model=sample_model).track('generation'):
                pytest.fail('revision adopted during output commit')
        from sdd.publication_operation import archive_plan
        archive_plan(tmp_cfg, dict(schema=1, units=[]), execution)
    with Execution(newer, object(), model=sample_model).track('generation'):
        pass
    assert len(revisions(tmp_cfg)) == 2


def test_changed_visual_input_needs_a_new_basis_and_live_edits_fail(tmp_cfg, sample_model):
    tmp_cfg.raw['visuals'] = dict(file='visuals.json')
    visual = tmp_cfg.root/'visuals.json'
    visual.write_text('{}', encoding='utf-8')
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass
    visual.write_text('{"changed": true}', encoding='utf-8')
    with pytest.raises(ValueError, match='new revision'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('changed diagram policy accepted without revision')
    bump(contract, kind='policy'); write()
    with pytest.raises(InputChanged):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            visual.write_text('{}', encoding='utf-8')


def test_other_operation_cannot_commit_before_rollback_finishes(tmp_cfg, sample_model):
    from sdd.execution_lock import AlreadyRunning
    configure(tmp_cfg, sample_model, ['device'])
    other = deepcopy(tmp_cfg)
    other.raw['publication']['operation_id'] = 'other-publication'
    first = Execution(tmp_cfg, object(), model=sample_model)
    with first.track('generation'):
        first.publication_contract.begin_output()
        with pytest.raises(AlreadyRunning, match='publication-output-commit'):
            with Execution(other, object(), model=sample_model).track('generation'):
                pass
    with Execution(other, object(), model=sample_model).track('generation'):
        pass


def test_failed_final_journal_save_rolls_back_output(tmp_cfg, sample_model, monkeypatch):
    configure(tmp_cfg, sample_model, ['device'])
    target = tmp_cfg.root/'owned.md'
    target.write_bytes(b'previous')
    execution = Execution(tmp_cfg, object(), model=sample_model)
    original = execution.persist
    def fail_completed():
        if execution.report['phases'][-1]['status'] == 'completed':
            raise OSError('journal unavailable')
        original()
    monkeypatch.setattr(execution, 'persist', fail_completed)
    with pytest.raises(OSError, match='journal unavailable'):
        with execution.track('generation'):
            execution.publication_contract.preserve_output(target, 'new')
            target.write_bytes(b'new\n')
    assert target.read_bytes() == b'previous'
    assert execution.report['phases'][-1]['status'] == 'failed'


def test_guard_checks_the_bound_transport_actually_invoked(tmp_cfg, sample_model):
    from sdd.llm import Agent
    configure(tmp_cfg, sample_model, ['device'])
    selected = Agent(tmp_cfg.agent, tmp_cfg.build_dir/'selected')
    wrong = deepcopy(tmp_cfg.agent)
    wrong.model = 'undeclared'
    alternate = Agent(wrong, tmp_cfg.build_dir/'alternate')
    execution = Execution(tmp_cfg, selected, model=sample_model)
    with pytest.raises(ValueError, match='Actual publication transport'):
        with execution.track('generation'):
            execution._chat(alternate.chat, 'system', 'user')
    assert not execution.report['calls']


@pytest.mark.parametrize('flag', [None, '--assume-unchanged', '--skip-worktree'])
def test_initial_dirty_evidence_cannot_claim_the_committed_source(tmp_cfg, sample_model, flag):
    source = tmp_cfg.source_root/'device.cpp'
    source.write_bytes(b'committed source')
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_cfg.source_root), *args], check=True,
            capture_output=True, text=True).stdout.strip()
    git('init'); git('add', 'device.cpp')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','source')
    sample_model.meta['source_commit'] = git('rev-parse','HEAD')
    configure(tmp_cfg, sample_model, ['device'])
    if flag:
        git('update-index', flag, 'device.cpp')
    sample_model.evidence = {'selected': dict(file='device.cpp', text='modified source')}
    source.write_bytes(b'modified source')
    with pytest.raises(ValueError, match='declared committed source'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('dirty source accepted as committed input')


def test_model_cannot_be_added_after_sealing_an_empty_basis(tmp_cfg, sample_model):
    configure(tmp_cfg, sample_model, ['device'])
    tmp_cfg.facts_path.unlink(missing_ok=True)
    execution = Execution(tmp_cfg, object())
    with execution.track('generation'):
        with pytest.raises(ValueError, match='sealed publication basis'):
            execution.publication_contract.select(sample_model, ['device'])


@pytest.mark.parametrize('setting,value', [
    ('budget', {'max_calls': 1}),
    ('reports', [dict(path='final.json', gate='before-export', producer='final-review', sha256='0'*64, bindings={'status':'passed'})]),
])
def test_publication_policy_changes_require_an_explicit_revision(tmp_cfg, sample_model, setting, value):
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass
    tmp_cfg.raw['publication'][setting] = value
    with pytest.raises(ValueError, match='new revision'):
        with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
            pytest.fail('publication policy changed without a revision')
    bump(contract, kind='policy'); write()
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass


@pytest.mark.parametrize('external_edit', [False, True])
@pytest.mark.parametrize('use_profile', [False, True])
def test_catalog_keeps_declared_basis_and_guards_commit_and_rollback(tmp_cfg, sample_model, monkeypatch, external_edit, use_profile):
    from sdd.localization_cli import prepare_catalog
    from sdd.generation_run import observed
    import sdd.localization_cli as catalogs
    sample_model.save(tmp_cfg.facts_path)
    tmp_cfg.raw['site'] = dict(english_catalog='english.json')
    if use_profile:
        from dataclasses import asdict
        selected = tmp_cfg.root/'translation-profile.yaml'
        selected.write_text(json.dumps(dict(agent=asdict(tmp_cfg.agent))), encoding='utf-8')
        tmp_cfg.paths['translation_profile'] = selected
    contract, write = configure(tmp_cfg, sample_model, ['device'])
    target = tmp_cfg.root/'english.json'
    original = b'{"strings": {"old": "original"}}'
    target.write_bytes(original)
    def render(cfg, out, **kwargs):
        assert cfg.site.english_catalog is None
        (out/'index.html').write_text('<p>설명입니다.</p>', encoding='utf-8')
        (out/'assets').mkdir()
        (out/'assets/search.json').write_text('[]', encoding='utf-8')
        return out
    def translate(cfg, catalog, agent):
        assert cfg.site.english_catalog == 'english.json'
        with Execution(cfg, object(), model=sample_model).track('translation'):
            pass
        return catalog
    saved = catalogs.save
    def save_and_invalidate(path, data, **kwargs):
        assert observed().publication_contract.output_lease is not None
        saved(path, data, **kwargs)
        if external_edit:
            path.write_bytes(b'user catalog edit')
        contract['reason'] = 'Changed after catalog replacement.'; write()
    monkeypatch.setattr('sdd.export_site._render_site', render)
    monkeypatch.setattr('sdd.translation.translate_missing', translate)
    monkeypatch.setattr(catalogs, 'save', save_and_invalidate)
    with pytest.raises(InputChanged):
        prepare_catalog(tmp_cfg, target, translate=True)
    assert target.read_bytes() == (b'user catalog edit' if external_edit else original)


@pytest.mark.parametrize('edit_original', [False, True])
def test_independent_audit_keeps_original_config_snapshot_under_same_revision(tmp_cfg, sample_model, monkeypatch, edit_original):
    import sdd.consistency as checks
    from dataclasses import asdict
    sample_model.save(tmp_cfg.facts_path)
    selected = tmp_cfg.root/'review-profile.yaml'
    selected.write_text(json.dumps(dict(agent=asdict(tmp_cfg.agent))), encoding='utf-8')
    tmp_cfg.paths['consistency_profile'] = selected
    groups = tmp_cfg.root/'contracts.yaml'
    groups.write_text(json.dumps(dict(contracts=[dict(id='fixed',question='Fixed task?',primary='device.md',documents=['device.md'],match='device')])), encoding='utf-8')
    tmp_cfg.paths['consistency_file'] = groups
    configure(tmp_cfg, sample_model, ['device'])
    with Execution(tmp_cfg, object(), model=sample_model).track('generation'):
        pass
    def audit(cfg, model, execution, configured):
        assert cfg._loaded_inputs == tmp_cfg._loaded_inputs
        assert execution.report['publication']['revision'] == 1
        if edit_original:
            original = tmp_cfg.root/'sdd.yaml'
            original.write_bytes(original.read_bytes()+b'\n# changed during independent review\n')
        with execution.document('consistency', []):
            return dict(status='passed', revision=execution.report['publication']['revision'],
                        audit_run=dict(id=execution.path.stem, document=len(execution.report['documents'])-1,
                                       phase=len(execution.report['phases'])-1))
    monkeypatch.setattr(checks, '_audit', audit)
    if edit_original:
        with pytest.raises(InputChanged):
            checks.audit(tmp_cfg, sample_model, object())
    else:
        assert checks.audit(tmp_cfg, sample_model, object())['revision'] == 1


def test_first_merge_pipeline_keeps_basis_through_translation_review_export_and_rollback(cli_units, tmp_cfg, monkeypatch):
    """Real entry points and receipts; only the CLI process is a test double."""
    import re
    from dataclasses import asdict
    from sdd.consistency import audit
    from sdd.export_site import export_site
    from sdd.localization_cli import prepare_catalog
    from sdd.site_build import verify_site
    import sdd.cli_agent as cli
    section, model, save, calls, state, agent = cli_units
    state['interrupt'] = False
    tmp_cfg.agent.max_input_chars = 48000
    tmp_cfg.raw['site'] = dict(english_catalog='english.json', translation_batch_size=12)
    selected = {}
    for role, path_key in [('translation', 'translation_profile'), ('review', 'consistency_profile')]:
        value = asdict(tmp_cfg.agent)
        value['model'] = 'fixture-'+role
        path = tmp_cfg.root/(role+'.yaml')
        path.write_text(json.dumps(dict(agent=value)), encoding='utf-8')
        tmp_cfg.paths[path_key] = path
        selected[role] = value
    contracts = tmp_cfg.root/'contracts.yaml'
    contracts.write_text(json.dumps(dict(contracts=[dict(id='lifetime', question='Who stops?',
        primary='device.md', documents=['device.md'], match='stop|prepare')])), encoding='utf-8')
    tmp_cfg.paths['consistency_file'] = contracts
    declaration, write = configure(tmp_cfg, model, ['device'])
    for role in selected:
        declaration['profiles'][role]['model'] = 'fixture-'+role
    write()
    original_run = cli.run
    roles = []
    def run(argv, **kwargs):
        prompt = kwargs['prompt']
        if 'Translate Korean to English;' in prompt:
            roles.append('translation')
            assert 'fixture-translation' in argv
            payload = json.loads(prompt.split('<user>\n',1)[1].split('\n</user>',1)[0])
            raw = dict(translations={key:('section-wide evidence ' if '절 전체 근거' in text else 'English must ')
                                     + ' '.join(re.findall(r'\{\{\d+\}\}', text))
                                     for key,text in payload['texts'].items()})
        elif 'Audit contracts across documents' in prompt:
            roles.append('review')
            assert 'fixture-review' in argv
            payload = json.loads(prompt.split('<user>\n',1)[1].split('\n</user>',1)[0])
            raw = dict(findings=[dict(claim_id=key, peers=[], status='compatible',
                condition='Fixture', actor='Fixture', timing='Fixture', scope='Fixture', reason='Fixture',
                sources=[dict(source_id=next(iter(payload['sources'])))]) for key in payload['claims']])
        else:
            return original_run(argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, json.dumps(dict(subtype='success',is_error=False,
                                            result=json.dumps(raw))), '')
    monkeypatch.setattr(cli, 'run', run)
    Generator(tmp_cfg, model, agent()).run()
    target = tmp_cfg.sdd_dir/'device.md'
    original = target.read_bytes()
    catalog = tmp_cfg.root/'english.json'
    assert prepare_catalog(tmp_cfg, catalog, translate=True)['missing_translations'] == 0
    assert audit(tmp_cfg, model, object())['status'] == 'passed'
    assert roles and roles.index('review') > roles.index('translation')
    assert tmp_cfg.agent.model == 'fixture-model'
    site = export_site(tmp_cfg)
    assert verify_site(site)['broken_links'] == 0
    assert target.read_bytes() == original
    # Retain a valid prior manifest with distinct producer metadata so this
    # failure cannot pass merely because repeated output bytes are identical.
    manifest = site/'site-manifest.json'
    prior_manifest = json.loads(manifest.read_bytes())
    prior_manifest['fixture_previous'] = 'restore this exact prior manifest'
    manifest.write_text(json.dumps(prior_manifest), encoding='utf-8')
    before = {p:p.read_bytes() for p in site.rglob('*') if p.is_file()}
    journals = {p:p.read_bytes() for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')}
    import sdd.state_io as state_io
    old_save = state_io.save
    def fail_after_manifest(path, data, **kwargs):
        old_save(path, data, **kwargs)
        if path == site/'site-manifest.json':
            assert path.read_bytes() != before[path]
            raise OSError('fixture final site acceptance failed')
    monkeypatch.setattr(state_io, 'save', fail_after_manifest)
    with pytest.raises(OSError, match='final site acceptance'):
        export_site(tmp_cfg)
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert all(p.read_bytes()==raw for p,raw in journals.items())
    assert target.read_bytes()==original
    assert len(revisions(tmp_cfg))==1
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert any(p['name']=='translation-preflight' and p['status']=='completed' for r in runs for p in r['phases'])
    assert any(p['status']=='failed' for r in runs for p in r['phases'])
