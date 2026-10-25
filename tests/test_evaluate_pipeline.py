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
