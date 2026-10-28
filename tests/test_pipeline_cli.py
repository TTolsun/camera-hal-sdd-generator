"""Exercise fresh CLI trials using source-aware fake subprocesses, without a model."""
import json
import subprocess
import sys

import pytest
import yaml

from sdd.evaluate_pipeline import evaluate
from sdd.document_metadata import split_frontmatter as _split
from sdd.generate import Generator
from sdd.llm import Agent
from sdd.provenance import verify_calls
from test_evaluate_pipeline import configure


def test_cli_model_and_arguments_enter_config_impact_without_render_only_redrafting(cli_trial, tmp_path, monkeypatch):
    from sdd.facts.model import KnowledgeModel
    from sdd.impact import config_changes
    from sdd.trial_workspace import clone_config
    cfg = cli_trial('codex', model='fixture-model')
    out = tmp_path/'execution-impact'
    evaluate(cfg, out)
    selected = clone_config(cfg, out)
    model = KnowledgeModel.load(selected.facts_path)
    monkeypatch.setattr(Agent, 'chat', lambda *a, **k: pytest.fail('Impact analysis must not call a model'))
    assert config_changes(selected, model) == {}
    selected.raw.setdefault('site', {})['title'] = 'Presentation only'
    assert config_changes(selected, model) == {}
    selected.agent.model = 'another-model'
    assert set(config_changes(selected, model)) == {'entry'}
    selected.agent.model = 'fixture-model'
    selected.agent.args = ['-c', 'model_reasoning_effort="high"']
    assert set(config_changes(selected, model)) == {'entry'}


@pytest.fixture
def cli_trial(tmp_cfg, tmp_path, monkeypatch):
    cfg = configure(tmp_cfg)
    cfg.agent.kind = 'cli'
    cfg.agent.model = ''
    cfg.agent.allow_direct_api = False
    cfg.agent.max_input_chars = 30000
    cfg.agent.timeout_sec = 10
    cfg.max_retries = 0
    section = dict(id='entry', title='초기화', kind='prose', output='overview.md',
        design_generation='llm', facts={'classes': []}, diagram={'enabled': False}, show_evidence=True,
        next={'title': '초기화', 'link': 'overview.md'},
        design_requirements=[{'id': 'start', 'question': '콜백을 어디에 저장합니까?'}],
        design_topics=[{'id': 'start', 'title': '콜백 저장', 'question': 'initialize()에서 콜백을 어디에 저장합니까?',
            'covers': ['start'], 'sources': [{'id': 'device', 'file': 'src/device/CameraDevice.cpp',
                'start': 'int CameraDevice::initialize(', 'end': '\n}\n'}]}])
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    cfg.raw['visuals'] = {'file': 'visuals.yaml', 'max_nodes': 2}
    (cfg.root / 'visuals.yaml').write_text(yaml.safe_dump({'schema': 1, 'sections': {'entry': [
        dict(id='callback', topic='start', kind='flow', generation='llm', title='콜백 저장',
             question='initialize()와 callbacks_의 관계는 무엇입니까?')]}}, allow_unicode=True), encoding='utf-8')
    script = tmp_path / 'fake_cli.py'
    script.write_text('''import json, sys, time
from pathlib import Path
prompt = sys.stdin.read()
runner, mode = sys.argv[1:3]
if mode == 'failed':
    sys.stderr.write('fake runner failed')
    sys.exit(2)
if mode == 'timeout':
    time.sleep(30)
if mode == 'incomplete':
    print(json.dumps({'type': 'text', 'part': {'text': 'partial'}}))
    sys.exit(0)
user = prompt.split('<user>\\n', 1)[1].rsplit('\\n</user>', 1)[0]
data, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
quote = next(b['quote_id'] for blocks in data['sources'].values() for b in blocks if 'quote_id' in b)
if 'kind' in data:
    answer = dict(nodes=[dict(id='initialize', symbol='initialize', label='초기화 함수',
        label_en='Initialize', shape='box', quote_ids=[quote]),
        dict(id='callbacks', symbol='callbacks_', label='콜백 저장 필드',
        label_en='Callback field', shape='box', quote_ids=[quote])],
        edges=[dict(**{'from': 'initialize', 'to': 'callbacks'}, label='콜백 저장',
        label_en='Store callbacks', condition_ref='always', quote_ids=[quote])])
else:
    answer = {'statements': [dict(text='initialize()에서 callbacks_에 콜백을 저장합니다.',
        quote_id=quote, covers=['start'], kind='behavior')]}
    if runner == 'codex':
        answer['statements'][0]['evidence'] = [quote.rsplit(':', 1)[0]]
text = json.dumps(answer, ensure_ascii=False)
if runner == 'hermes':
    print(text)
elif runner == 'claude':
    print(json.dumps(dict(type='result', subtype='success', is_error=False, result=text)))
elif runner == 'codex':
    print(json.dumps(dict(type='turn.started')))
    print(json.dumps(dict(type='item.completed', item=dict(type='agent_message', text=text))))
    print(json.dumps(dict(type='turn.completed', usage=dict(output_tokens=10))))
else:
    print(json.dumps(dict(type='text', part={'text': text})))
    print(json.dumps(dict(type='step_finish', part={'reason': 'stop'})))
''', encoding='utf-8')
    monkeypatch.setattr(Agent, '_post', lambda *a: pytest.fail('CLI trial must not call HTTP'))
    monkeypatch.setattr(Agent, '_get', lambda *a: pytest.fail('CLI trial must not probe HTTP'))

    def select(runner='hermes', mode='success', model=''):
        cfg.agent.runner = runner
        cfg.agent.model = model
        cfg.agent.command = [sys.executable, str(script), runner, mode]
        return cfg

    return select


@pytest.mark.parametrize('runner', ['hermes', 'opencode', 'claude', 'codex'])
@pytest.mark.parametrize('model', ['', 'chosen/model'])
def test_fresh_cli_trial_generates_verifies_audits_and_repeats(cli_trial, tmp_path, runner, model):
    cfg = cli_trial(runner, model=model)
    inputs = cfg.facts_path.read_bytes()
    cfg.sdd_dir.mkdir()
    sentinel = cfg.sdd_dir / 'operational.md'
    sentinel.write_bytes(b'keep operational manuscript')
    out = tmp_path / 'trial'
    report = evaluate(cfg, out)
    assert all(s['status'] == 'passed' for s in report['stages']), report['stages']
    assert report['stages'][-1]['stage'] == 'repeat-site'
    assert report['runner'] == runner and report['model'] == model
    assert report['model_selection'] == ('explicit' if model else 'cli-default')
    assert report['agent_label'] == f'cli/{runner}/{model or "cli-default"}'
    assert report['semantic_review'] == report['human_approval'] == 'pending'
    assert report['publishable'] is False
    result = next(s['result'] for s in report['stages'] if s['stage'] == 'model-provenance')
    assert result['verified_cli_calls'] == 2 and result['verified_http_calls'] == 0
    assert result['documents'] == result['topics'] == result['statements'] == result['visuals'] == 1
    metadata, _ = _split((out / 'manuscripts/overview.md').read_text(encoding='utf-8'))
    assert metadata['generated_design']['topic_agents'] == {'start': report['agent_label']}
    assert metadata['generated_visuals']['records']['callback']['producer'] == report['agent_label']
    assert cfg.facts_path.read_bytes() == inputs
    assert sentinel.read_bytes() == b'keep operational manuscript'
    assert (out / 'site/overview.html').exists()
    assert json.loads((out / 'evaluation.json').read_text(encoding='utf-8')) == report
    # Exercise the standalone verifier's CLI argparse and real archive reading.
    result = subprocess.run([sys.executable, '-m', 'sdd.provenance', '--facts', str(out / 'facts/facts.json'),
        '--manuscripts', str(out / 'manuscripts'), '--calls', str(out / 'build/prompts/calls'),
        '--provider', 'cli', '--runner', runner, *(['--model', model] if model else [])],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['verified_cli_calls'] == 2


@pytest.mark.parametrize('mode', ['missing', 'failed', 'timeout', 'incomplete'])
def test_cli_trial_failure_records_error_without_publishing_or_replacing_inputs(cli_trial, tmp_path, mode):
    cfg = cli_trial('opencode' if mode == 'incomplete' else 'hermes', mode)
    if mode == 'missing':
        cfg.agent.command = ['sdd-nonexistent-cli']
    if mode == 'timeout':
        cfg.agent.timeout_sec = 0.2
    inputs = cfg.facts_path.read_bytes()
    out = tmp_path / 'failed-trial'
    report = evaluate(cfg, out)
    assert report['results'][0]['automatic_checks'] == 'failed'
    assert report['stages'][-1]['stage'] == 'generate/entry'
    assert not (out / 'site').exists()
    assert report['publishable'] is False and report['human_approval'] == 'pending'
    assert cfg.facts_path.read_bytes() == inputs
    assert not list((out / 'build/prompts/calls').rglob('*.receipt.json'))
    assert json.loads((out / 'evaluation.json').read_text(encoding='utf-8')) == report


@pytest.mark.parametrize('tamper', ['response', 'stdout', 'runner', 'topic', 'visual'])
def test_cli_provenance_failure_stops_before_site(cli_trial, tmp_path, monkeypatch, tamper):
    cfg = cli_trial()
    original = Generator.run

    def corrupt(self, *args, **kwargs):
        paths = original(self, *args, **kwargs)
        calls = self.cfg.build_dir / 'prompts/calls'
        receipt_path = next(calls.rglob('*.receipt.json'))
        if tamper == 'response':
            receipt_path.with_name(receipt_path.name.replace('.receipt.json', '.response.txt')).write_text(
                'changed response', encoding='utf-8')
        elif tamper in ('runner', 'stdout'):
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if tamper == 'runner':
                receipt['provider']['runner'] = 'claude'
                receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
            else:
                (calls.parent / receipt['provider']['stdout_path']).write_text('changed stdout', encoding='utf-8')
        else:
            page = paths[0]
            metadata, body = _split(page.read_text(encoding='utf-8'))
            if tamper == 'topic':
                metadata['generated_design']['topic_agents']['start'] = 'cli/claude/cli-default'
            else:
                metadata['generated_visuals']['records']['callback']['producer'] = 'cli/claude/cli-default'
            page.write_text('---\n' + yaml.safe_dump(metadata, allow_unicode=True)
                            + '---\n' + body, encoding='utf-8')
        return paths

    monkeypatch.setattr(Generator, 'run', corrupt)
    out = tmp_path / 'tampered-trial'
    report = evaluate(cfg, out)
    assert report['stages'][-1]['stage'] == 'model-provenance'
    assert report['stages'][-1]['status'] == 'failed'
    assert not (out / 'site').exists() and report['publishable'] is False


def test_cli_resume_is_refused_before_output_or_execution(cli_trial, tmp_path, monkeypatch):
    cfg = cli_trial()
    monkeypatch.setattr('sdd.cli_agent.run', lambda *a, **kw: pytest.fail('Resume must not execute CLI'))
    monkeypatch.setattr('sdd.evaluate_pipeline.shutil.copy2', lambda *a, **kw: pytest.fail('No input copies'))
    out = tmp_path / 'resume'
    with pytest.raises(ValueError, match='재개를 지원하지'):
        evaluate(cfg, out, previous=tmp_path / 'previous')
    assert not out.exists()


def test_http_full_trial_requires_explicit_opt_in_before_writing(cli_trial, tmp_path):
    cfg = cli_trial()
    cfg.agent.kind = 'ollama'
    with pytest.raises(ValueError, match='allow_direct_api'):
        evaluate(cfg, tmp_path / 'http-trial')
    assert not (tmp_path / 'http-trial').exists()


def test_cli_provenance_requires_runner_and_refuses_reuse(tmp_path):
    from sdd.facts.model import KnowledgeModel
    for kwargs in ({}, {'runner': 'hermes', 'allow_reused': True}):
        with pytest.raises(ValueError, match='selected runner and fresh calls'):
            verify_calls(KnowledgeModel(), tmp_path / 'manuscripts', tmp_path / 'calls',
                         provider='cli', model_name='', **kwargs)
