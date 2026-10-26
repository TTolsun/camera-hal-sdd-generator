import json
from pathlib import Path
import subprocess

import pytest
import yaml

from sdd.evidence import collect
from sdd.evaluate_pipeline import evaluate
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator

ROOT = Path(__file__).resolve().parents[1]


def configure(cfg):
    cfg.agent.kind = 'ollama'
    cfg.source_root = ROOT / 'examples/mini-hal'
    cfg.raw['documentation'] = {'enabled': True}
    cfg.sections_file.write_bytes((cfg.source_root / 'config/reader-sections.yaml').read_bytes())
    cfg.scenarios_file.write_text('scenarios: []\n', encoding='utf-8')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    model = KnowledgeModel(meta={'source_commit': commit})
    collect(cfg, model)
    model.save(cfg.facts_path)
    return cfg


def test_complete_isolated_trial_audits_builds_and_repeats(tmp_cfg, tmp_path):
    cfg = configure(tmp_cfg)
    inputs = cfg.facts_path.read_bytes()
    out = tmp_path / 'trial'
    report = evaluate(cfg, out)
    assert len(report['results']) == 4
    assert all(row['automatic_checks'] == 'passed' for row in report['results'])
    assert report['stages'][-1]['stage'] == 'repeat-site'
    assert all(stage['status'] == 'passed' for stage in report['stages'])
    assert report['human_approval'] == report['semantic_review'] == 'pending'
    assert report['publishable'] is False
    assert json.loads((out / 'evaluation.json').read_text(encoding='utf-8')) == report
    assert cfg.facts_path.read_bytes() == inputs and not cfg.sdd_dir.exists()
    snapshot = yaml.safe_load((out / 'sdd.yaml').read_text(encoding='utf-8'))
    assert snapshot['output']['sdd_dir'] == str(out / 'manuscripts')
    assert (out / 'site/vendor-contract.html').exists()


def test_failed_section_is_recorded_and_does_not_build_or_replace_inputs(tmp_cfg, tmp_path, monkeypatch):
    cfg = configure(tmp_cfg)
    cfg.sdd_dir.mkdir()
    sentinel = cfg.sdd_dir / 'operational.md'
    sentinel.write_bytes(b'operational manuscript')
    original = Generator.run
    def failing(self, sections):
        if sections == ['vendor-contract']:
            raise ValueError('A model response failed the evidence check')
        return original(self, sections)
    monkeypatch.setattr('sdd.evaluate_pipeline.Generator.run', failing)
    out = tmp_path / 'trial'
    report = evaluate(cfg, out)
    assert len(report['results']) == 4  # Later sections still get exercised.
    failed = [row for row in report['results'] if row['automatic_checks'] == 'failed']
    assert failed[0]['section'] == 'vendor-contract'
    assert not (out / 'site').exists()
    assert sentinel.read_bytes() == b'operational manuscript'
    assert json.loads((out / 'evaluation.json').read_text(encoding='utf-8')) == report


def test_trial_refuses_canned_answers_and_existing_outputs(tmp_cfg, tmp_path):
    with pytest.raises(ValueError, match='실제'):
        evaluate(tmp_cfg, tmp_path / 'trial')
    tmp_cfg.agent.kind = 'response-bundle'
    with pytest.raises(ValueError, match='실제'):
        evaluate(tmp_cfg, tmp_path / 'trial')
    tmp_cfg.agent.kind = 'ollama'
    for out in (tmp_cfg.root, tmp_cfg.source_root / 'trial', tmp_cfg.sdd_dir / 'trial',
                tmp_cfg.facts_dir / 'trial'):
        with pytest.raises(ValueError, match='새 디렉터리'):
            evaluate(tmp_cfg, out)


def test_evidence_failure_keeps_machine_readable_report(tmp_cfg, tmp_path):
    tmp_cfg.agent.kind = 'ollama'
    report = evaluate(tmp_cfg, tmp_path / 'trial')
    assert report['stages'][-1]['stage'] == 'evidence'
    assert report['stages'][-1]['status'] == 'failed'
    assert report['results'] == [] and report['publishable'] is False


def test_trial_validates_output_paths_before_writing_even_without_lifecycle_policy(tmp_cfg, tmp_path):
    cfg = configure(tmp_cfg)
    cfg.raw['documentation']['enabled'] = False
    data = yaml.safe_load(cfg.sections_file.read_text(encoding='utf-8'))
    data['sections'][0]['output'] = '../../operational.md'
    cfg.sections_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    out = tmp_path / 'trial'
    sentinel = tmp_path / 'operational.md'
    sentinel.write_text('keep', encoding='utf-8')
    report = evaluate(cfg, out)
    assert report['stages'][-1]['stage'] == 'configuration'
    assert report['stages'][-1]['status'] == 'failed'
    assert report['results'] == [] and not (out / 'manuscripts').exists()
    assert sentinel.read_text(encoding='utf-8') == 'keep'


def model_config(tmp_cfg, monkeypatch):
    from sdd.llm import Agent
    cfg = configure(tmp_cfg)
    cfg.agent.max_input_chars = 20000
    section = {'id': 'entry', 'title': '시작', 'kind': 'prose', 'output': 'overview.md',
               'design_generation': 'llm', 'facts': {'classes': []}, 'diagram': {'enabled': False},
               'design_requirements': [{'id': 'start', 'question': '처음 동작은 무엇입니까?'}],
               'design_topics': [{'id': 'start', 'title': '진입점', 'question': '초기화를 설명하세요.',
                   'covers': ['start'], 'sources': [{'id': 'device', 'file': 'src/device/CameraDevice.cpp',
                     'start': '#include "device/CameraDevice.h"', 'end': '}  // namespace halcam'}]}]}
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    calls = []
    def post(self, url, body):
        calls.append(body)
        user = body['messages'][1]['content']
        payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
        quote_id = next(b['quote_id'] for b in payload['sources']['device'] if 'quote_id' in b)
        return {'done_reason': 'stop', 'message': {'content': json.dumps({'statements': [{
            'text': 'initialize()에서 콜백을 등록합니다.', 'quote_id': quote_id,
            'covers': ['start'], 'kind': 'behavior'}]}, ensure_ascii=False)}}
    monkeypatch.setattr(Agent, '_post', post)
    return cfg, calls


def test_repair_preserves_http_provenance_and_regenerates_changed_questions(tmp_cfg, tmp_path, monkeypatch):
    cfg, calls = model_config(tmp_cfg, monkeypatch)
    first = tmp_path / 'first'
    assert evaluate(cfg, first)['stages'][-1]['stage'] == 'repeat-site'
    assert len(calls) == 1
    second = tmp_path / 'second'
    report = evaluate(cfg, second, previous=first)
    assert report['mode'] == 'repair' and len(calls) == 1
    assert all(row['status'] == 'passed' for row in report['stages'])
    assert report['human_approval'] == 'pending' and report['publishable'] is False
    data = yaml.safe_load(cfg.sections_file.read_text(encoding='utf-8'))
    data['sections'][0]['design_topics'][0]['question'] = '초기화 함수가 무엇을 하는지 설명하세요.'
    cfg.sections_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    third = evaluate(cfg, tmp_path / 'third', previous=second)
    assert all(row['status'] == 'passed' for row in third['stages']) and len(calls) == 2


def test_failed_section_can_revalidate_real_http_units_on_repair(tmp_cfg, tmp_path, monkeypatch):
    cfg, calls = model_config(tmp_cfg, monkeypatch)
    original = Generator.run
    def fail_after_generation(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        for path in result:
            path.unlink()
        raise ValueError('Simulated failure after a real HTTP answer')
    monkeypatch.setattr(Generator, 'run', fail_after_generation)
    first = tmp_path / 'first'
    assert evaluate(cfg, first)['results'][0]['automatic_checks'] == 'failed'
    assert len(calls) == 1
    monkeypatch.setattr(Generator, 'run', original)
    report = evaluate(cfg, tmp_path / 'repair', previous=first)
    assert all(row['status'] == 'passed' for row in report['stages'])
    assert len(calls) == 1
    assert report['results'][0]['replayed_units'][0]['topic'] == 'start'
    assert report['publishable'] is False and report['human_approval'] == 'pending'


def test_interrupted_trial_reuses_only_recorded_hash_checked_manuscripts(tmp_cfg, tmp_path):
    cfg = configure(tmp_cfg)
    first = tmp_path / 'first'
    report = evaluate(cfg, first)
    unrecorded = report['results'].pop()
    for item in unrecorded['manuscripts']:
        (first / item['path']).write_text('UNRECORDED CONTENT', encoding='utf-8')
    (first / 'evaluation.json').write_text(json.dumps(report), encoding='utf-8')
    second = tmp_path / 'repair'
    repaired = evaluate(cfg, second, previous=first)
    resume = next(row for row in repaired['stages'] if row['stage'] == 'resume-input')
    assert resume['status'] == 'passed' and resume['result']['previous_generation_complete'] is False
    assert all(row['status'] == 'passed' for row in repaired['stages'])
    assert all('UNRECORDED CONTENT' not in p.read_text(encoding='utf-8') for p in (second / 'manuscripts').rglob('*.md'))


@pytest.mark.parametrize('change', ['manuscript', 'response', 'source', 'model', 'incomplete'])
def test_repair_refuses_tampered_mismatched_or_incomplete_trials(tmp_cfg, tmp_path, monkeypatch, change):
    cfg, calls = model_config(tmp_cfg, monkeypatch)
    first = tmp_path / 'first'
    original = evaluate(cfg, first)
    if change == 'manuscript':
        with (first / 'manuscripts/overview.md').open('a', encoding='utf-8') as stream:
            stream.write('Modified outside generation.')
    elif change == 'response':
        next((first / 'build/prompts/calls').rglob('*.response.txt')).write_text('Changed response.', encoding='utf-8')
    else:
        if change == 'source':
            original['source_commit'] = 'a' * 40
        elif change == 'model':
            original['model'] = 'another-model'
        else:
            original['results'] = []
        (first / 'evaluation.json').write_text(json.dumps(original), encoding='utf-8')
    report = evaluate(cfg, tmp_path / 'repair', previous=first)
    assert report['stages'][-1]['stage'] == 'resume-input'
    assert report['stages'][-1]['status'] == 'failed' and len(calls) == 1
    assert not (tmp_path / 'repair/site').exists()


def test_repair_generates_all_scenario_children_when_prior_report_only_has_index(tmp_cfg, tmp_path, sample_model):
    cfg = configure(tmp_cfg)
    data = yaml.safe_load(cfg.sections_file.read_text(encoding='utf-8'))
    data['sections'].append(dict(id='flows', title='호출 흐름', kind='per-scenario',
        output='scenarios/index.md', narration='facts', diagram={'enabled': False}))
    cfg.sections_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    cfg.scenarios_file.write_text(yaml.safe_dump({'scenarios': [dict(id='process_capture_request',
        title='캡처 요청 처리', entry='CameraDevice::processCaptureRequest(camera3_capture_request_t *)')]}), encoding='utf-8')
    model = KnowledgeModel.load(cfg.facts_path)
    model.scenarios = sample_model.scenarios
    model.save(cfg.facts_path)
    first = tmp_path / 'first'
    report = evaluate(cfg, first)
    assert all(s['status'] == 'passed' for s in report['stages']), [s for s in report['stages'] if s['status'] != 'passed']
    row = next(r for r in report['results'] if r['section'] == 'flows')
    assert len(row['manuscripts']) == 2
    # Reproduce the old repair bug's recorded index-only output.
    child = first / 'manuscripts/scenarios/process_capture_request.md'
    child.unlink()
    row['manuscripts'] = [m for m in row['manuscripts'] if m['path'].endswith('/index.md')]
    (first / 'evaluation.json').write_text(json.dumps(report), encoding='utf-8')
    second = tmp_path / 'repair'
    repaired = evaluate(cfg, second, previous=first)
    assert all(s['status'] == 'passed' for s in repaired['stages'])
    assert (second / 'manuscripts/scenarios/process_capture_request.md').exists()
    assert len(next(r for r in repaired['results'] if r['section'] == 'flows')['manuscripts']) == 2
