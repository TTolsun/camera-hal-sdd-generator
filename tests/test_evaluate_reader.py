import json
import hashlib

import pytest

from sdd.evaluate_reader import evaluate


def configured(tmp_cfg, monkeypatch):
    tmp_cfg.agent.kind = 'ollama'
    monkeypatch.setattr(type(tmp_cfg), 'sections', lambda _: [dict(id='overview', title='Overview', design_generation='llm')])
    return tmp_cfg


def test_evaluation_rejects_canned_answers(tmp_cfg, tmp_path):
    with pytest.raises(ValueError, match='연결'):
        evaluate(tmp_cfg, ['overview'], tmp_path / 'trial')


def test_evaluation_protects_operational_inputs(tmp_cfg, tmp_path, monkeypatch):
    cfg = configured(tmp_cfg, monkeypatch)
    for path in [cfg.root, cfg.source_root/'trial', cfg.sdd_dir/'trial', cfg.facts_dir/'trial']:
        with pytest.raises(ValueError, match='새 디렉터리'):
            evaluate(cfg, ['overview'], path)


@pytest.mark.parametrize(('kind', 'prompt_path'), [('ollama', 'prompts'), ('cli', 'build/prompts')])
def test_evaluation_records_failure_without_publishing(tmp_cfg, tmp_path, sample_model, monkeypatch,
                                                        kind, prompt_path):
    cfg = configured(tmp_cfg, monkeypatch)
    cfg.agent.kind = kind
    sample_model.save(cfg.facts_path)
    monkeypatch.setattr('sdd.evaluate_reader.collect', lambda *_: None)
    def fail(self, selected):
        assert self.cfg.sdd_dir != cfg.sdd_dir
        raise ValueError('missing evidence')
    monkeypatch.setattr('sdd.evaluate_reader.Generator.run', fail)
    out = tmp_path/'trial'
    def agent_factory(settings, dump_dir):
        assert settings.kind == kind
        assert dump_dir == out / prompt_path
        return object()
    report = evaluate(cfg, ['overview'], out, agent_factory=agent_factory)
    assert report['results'][0]['automatic_checks'] == 'failed'
    assert report['human_approval'] == 'pending' and report['publishable'] is False
    assert json.loads((out/'evaluation.json').read_text(encoding='utf-8')) == report
    assert (out/'sections.yaml').read_bytes() == cfg.sections_file.read_bytes()
    assert report['sections_sha256'] == hashlib.sha256((out/'sections.yaml').read_bytes()).hexdigest()
    assert 'answer_contracts.py' in report['generator_files_sha256']
    assert report['settings']['think'] == cfg.agent.think
    assert not cfg.sdd_dir.exists()
