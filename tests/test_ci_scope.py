"""Exercise CI routing against actual Git histories, including unsafe shortcuts."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_scope', ROOT / 'ci/scope.py')
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def commit(repo, files):
    for path, value in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if value is None:
            target.unlink()
        else:
            target.write_text(value, encoding='utf-8')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'fixture')
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-b', 'main')
    git(tmp_path, 'config', 'user.name', 'CI routing test')
    git(tmp_path, 'config', 'user.email', 'ci@example.invalid')
    commit(tmp_path, {'README.md': 'baseline', 'src/runtime.py': 'baseline'})
    return tmp_path


def push(repo, base):
    head = git(repo, 'rev-parse', 'HEAD')
    return scope.route(repo, 'push', dict(ref='refs/heads/main', before=base, after=head), head)


def test_real_merge_uses_entire_pr_instead_of_latest_commit(repo):
    base = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-qb', 'feature')
    commit(repo, {'src/runtime.py': 'changed runtime'})
    head = commit(repo, {'docs/guide.md': 'latest commit is documentation'})
    git(repo, 'checkout', 'main')
    git(repo, 'merge', '--no-ff', '-m', 'tested merge', 'feature')
    checkout = git(repo, 'rev-parse', 'HEAD')
    event = dict(pull_request=dict(base=dict(sha=base), head=dict(sha=head)))
    report = scope.route(repo, 'pull_request', event, checkout)
    assert report['scope'] == 'full'
    assert {x['path'] for x in report['changes']} == {'docs/guide.md', 'src/runtime.py'}
    # A head checkout, or a different base in the webhook, is never docs-only.
    assert scope.route(repo, 'pull_request', event, head)['scope'] == 'full'
    event['pull_request']['base']['sha'] = head
    assert scope.route(repo, 'pull_request', event, checkout)['scope'] == 'full'


def test_real_docs_pr_merge_and_push(repo):
    base = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-qb', 'feature')
    head = commit(repo, {'docs/records/guide.md': 'documentation'})
    git(repo, 'checkout', 'main')
    git(repo, 'merge', '--no-ff', '-m', 'tested merge', 'feature')
    checkout = git(repo, 'rev-parse', 'HEAD')
    report = scope.route(repo, 'pull_request', dict(pull_request=dict(
        base=dict(sha=base), head=dict(sha=head))), checkout)
    assert report['scope'] == 'docs'
    assert push(repo, base)['scope'] == 'docs'


@pytest.mark.parametrize('path', [
    'AGENTS.md', 'DESIGN.md', 'docs/AGENTS.md', 'docs/concepts/DESIGN.md',
    'docs/reference/CLAUDE.md', 'style/README.md', 'prompts/a.md', 'templates/a.md',
    'skills/a/SKILL.md', 'docs/inhouse/import-agent.md', 'examples/inhouse-template/README.md',
    'docs/concepts/site.md', 'docs/concepts/reader-quality.md',
    'docs/concepts/publication-inputs.md', 'docs/libcamera/records/evidence.md',
    'docs/records/evidence.json', 'docs/guide.yaml', '.github/workflows/tests.yml',
    'ci/scope.py', 'tests/test_anything.py', 'unknown.md',
])
def test_policy_execution_inputs_and_unknown_paths_require_full(path):
    assert scope.classify([dict(path=path, status='M', old_mode='100644',
                                new_mode='100644')])[0] == 'full'


@pytest.mark.parametrize('path', ['README.md', 'ci/README.md', 'docs/guide.md',
    'docs/concepts/guide.md', 'docs/reference/guide.md', 'docs/records/guide.md',
    'docs/libcamera/guide.md', 'docs/한글 guide.md'])
def test_allowlisted_documentation(path):
    assert scope.documentation(path)


def test_rename_out_of_runtime_cannot_hide_deleted_source(repo):
    base = git(repo, 'rev-parse', 'HEAD')
    (repo / 'docs').mkdir()
    git(repo, 'mv', 'src/runtime.py', 'docs/moved.md')
    git(repo, 'commit', '-qm', 'rename')
    report = push(repo, base)
    assert report['scope'] == 'full'
    assert {x['path'] for x in report['changes']} == {'src/runtime.py', 'docs/moved.md'}


def test_docs_deletion_and_rename_are_complete(repo):
    base = commit(repo, {'docs/old.md': 'old', 'docs/remove.md': 'remove'})
    (repo / 'docs/old.md').rename(repo / 'docs/new.md')
    commit(repo, {'docs/remove.md': None})
    report = push(repo, base)
    assert report['scope'] == 'docs'
    assert {x['path'] for x in report['changes']} == {'docs/old.md', 'docs/new.md', 'docs/remove.md'}


@pytest.mark.parametrize('mode', ['100755', '120000', '160000'])
def test_nonordinary_file_modes_require_full(mode):
    assert scope.classify([dict(path='docs/guide.md', status='M',
                               old_mode='100644', new_mode=mode)])[0] == 'full'


def test_more_than_api_file_limit_and_unicode_are_not_truncated(repo):
    base = git(repo, 'rev-parse', 'HEAD')
    files = {f'docs/guide-{i:03}.md': 'documentation' for i in range(350)}
    files['docs/한글 guide.md'] = 'text'
    files['src/zz-last.py'] = 'runtime change'
    commit(repo, files)
    report = push(repo, base)
    assert report['scope'] == 'full'
    assert len(report['changes']) == 352
    assert any(x['path'] == 'docs/한글 guide.md' for x in report['changes'])


def test_missing_history_empty_diff_manual_and_tags_fall_back_to_full(repo):
    head = git(repo, 'rev-parse', 'HEAD')
    assert push(repo, head)['reason'] == 'empty-diff'
    assert push(repo, '0' * 40)['reason'] == 'unavailable-or-unverified-history'
    assert push(repo, '--help')['scope'] == 'full'
    for event in ['workflow_dispatch', 'unknown']:
        assert scope.route(repo, event, {}, head)['scope'] == 'full'
    assert scope.route(repo, 'push', dict(ref='refs/tags/release'), head)['scope'] == 'full'
    assert scope.route(repo, 'pull_request', {}, head)['scope'] == 'full'


def test_cli_persists_selected_commits_paths_and_safe_output(repo):
    base = git(repo, 'rev-parse', 'HEAD')
    head = commit(repo, {'docs/한글 guide.md': 'guide'})
    event = repo / 'event.json'
    event.write_text(json.dumps(dict(ref='refs/heads/main', before=base, after=head)), encoding='utf-8')
    output, summary, record = [repo / name for name in ['output', 'summary', 'record.json']]
    env = dict(os.environ, GITHUB_EVENT_PATH=str(event), GITHUB_EVENT_NAME='push',
               GITHUB_SHA=head, GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
    subprocess.run([sys.executable, str(ROOT / 'ci/scope.py'), '--out', str(record)],
                   cwd=repo, env=env, check=True, capture_output=True)
    result = json.loads(record.read_text(encoding='utf-8'))
    assert (result['base'], result['head'], result['scope']) == (base, head, 'docs')
    assert result['changes'][0]['path'] == 'docs/한글 guide.md'
    assert output.read_text(encoding='utf-8') == 'scope=docs\n'
    assert '한글' not in summary.read_text(encoding='utf-8')


def test_workflow_keeps_required_contexts_and_full_validation_with_fail_closed_routing():
    workflow = yaml.load((ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8'),
                         Loader=yaml.BaseLoader)
    assert workflow['on']['push'] == dict(branches=['main'], tags=['**'])
    assert {'pull_request', 'workflow_dispatch'} <= workflow['on'].keys()
    assert workflow['concurrency']['cancel-in-progress'] == "${{ github.event_name == 'pull_request' }}"
    assert 'github.run_id' in workflow['concurrency']['group']
    test = workflow['jobs']['test']
    assert test['needs'] == 'scope' and test['if'] == '${{ !cancelled() }}'
    assert test['strategy']['matrix'] == dict(os=['ubuntu-latest', 'windows-latest'], python=['3.11', '3.14'])
    steps = {x.get('name'): x for x in test['steps'] if x.get('name')}
    assert "== 'success'" in steps['Require successful routing']['run']
    assert '--no-sync pytest -q --junitxml' in steps['Full regression suite']['run']
    assert 'test_first_merge_pipeline' in steps['Publication pre-merge integration']['run']
    assert 'test_docs_links.py' in steps['Documentation validation']['run']
    assert steps['Preserve validation evidence']['if'] == 'always()'
