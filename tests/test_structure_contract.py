"""External contracts captured before #141; no live model calls."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from sdd.config import load
from sdd.generated_design import generate
from sdd.trial_workspace import clone_config, write_snapshot
from test_generated_design import generated


@pytest.mark.parametrize('example', ['libcamera', 'mini-hal', 'inhouse-template'])
def test_example_effective_config_round_trip(example, tmp_path):
    root = Path(__file__).resolve().parents[1]
    cfg = load(root / 'examples' / example / 'sdd.yaml')
    out = tmp_path / 'trial'
    out.mkdir()
    trial = clone_config(cfg, out)
    restored = load(write_snapshot(trial, out / 'sdd.yaml'))
    for name in ('agent', 'source_root', 'compile_commands', 'paths', 'facts_dir',
                 'sdd_dir', 'diagrams_dir', 'require_citations', 'max_retries', 'package_depth'):
        assert getattr(restored, name) == getattr(trial, name)


def test_named_local_merge_preserves_false_zero_null_and_relative_paths(tmp_path):
    main = tmp_path / 'sdd.claude.yaml'
    main.write_text(yaml.safe_dump({'source': {'root': 'code'},
        'agent': {'kind': 'cli', 'runner': 'hermes', 'max_output_tokens': 1500},
        'review': {'max_retries': 2, 'require_citations': True}, 'site': {'enabled': True}}))
    main.with_name('sdd.claude.local.yaml').write_text(yaml.safe_dump({
        'agent': {'runner': 'claude', 'model': 'claude-haiku-5-5', 'args': ['--effort', 'high'],
                  'max_output_tokens': 0, 'think': False},
        'review': {'max_retries': 0, 'require_citations': False}, 'site': None}))
    cfg = load(main)
    assert cfg.source_root == (tmp_path / 'code').resolve()
    assert cfg.agent.runner == 'claude' and cfg.agent.args == ['--effort', 'high']
    assert cfg.agent.model == 'claude-haiku-5-5' and cfg.agent.max_output_tokens == 0
    assert cfg.max_retries == 0 and cfg.require_citations is False
    assert cfg.raw['site'] is None


def test_configuration_views_follow_trial_mutations_and_preserve_unknown_keys(tmp_cfg):
    tmp_cfg.raw['site'] = {'translation_batch_size': 0, 'future_key': 'retained'}
    with pytest.raises(ValueError, match='translation_batch_size'):
        tmp_cfg.site.batch_size()
    tmp_cfg.raw['site']['translation_batch_size'] = 3
    assert tmp_cfg.site.batch_size() == 3
    assert tmp_cfg.raw['site']['future_key'] == 'retained'
    tmp_cfg.raw['review']['design_grounding'] = 'false'
    with pytest.raises(ValueError, match='boolean'):
        tmp_cfg.review.grounding({})
    assert tmp_cfg.review.grounding({'design_grounding': False}) is False


@pytest.mark.parametrize('values', [{}, {'design_revision': False, 'answer_cache': False},
                                   {'design_revision': 0, 'answer_cache': 0},
                                   {'design_revision': 'false', 'answer_cache': 'false'}])
def test_legacy_review_gate_values_are_not_coerced(tmp_cfg, values):
    tmp_cfg.raw['review'] = values
    assert tmp_cfg.review.design_revision == values.get('design_revision', False)
    assert tmp_cfg.review.answer_cache == values.get('answer_cache', False)


@pytest.mark.parametrize('group', ['automation', 'visuals', 'documentation'])
def test_explicit_null_optional_objects_keep_existing_rejection(tmp_cfg, group):
    tmp_cfg.raw[group] = None
    with pytest.raises(ValueError):
        view = getattr(tmp_cfg, group)
        if group == 'documentation':
            view.settings()


@pytest.mark.parametrize('kind', ['cli', 'ollama', 'openai-compatible', 'response-bundle'])
@pytest.mark.parametrize('mode', ['standard', 'focused'])
def test_frozen_generation_requests_results_and_origin(tmp_cfg, generated, kind, mode):
    section, model, _, draft = generated
    tmp_cfg.agent.kind = kind
    tmp_cfg.agent.model = 'test-model'
    tmp_cfg.raw['review'] = {'design_prompt': mode}
    calls = []
    class Recorded:
        def chat(self, system, user, **options):
            calls.append(dict(system=system, user=user, options=options))
            return json.dumps({'statements': [draft.statement]}, ensure_ascii=False)
    _, resolved, report, artifact = generate(tmp_cfg, model, Recorded(), copy.deepcopy(section))
    if kind == 'cli':
        from sdd.cli_checkpoint import validation_policy, style_policy
        assert artifact.pop('validation_policy') == validation_policy()
        assert artifact.pop('style_policy') == style_policy(tmp_cfg)
    stable = {'calls': calls, 'resolved': resolved, 'report': report, 'artifact': artifact}
    actual = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    # #138 intentionally changes native schemas, lexical coverage instructions
    # and focused obligations. Keep the old #141 capture as historical evidence.
    fixture = Path(__file__).parent / 'fixtures' / 'generation-138.json'
    expected = json.loads(fixture.read_text(encoding='utf-8'))
    assert actual == expected[f'{kind}/{mode}']


def test_split_validator_remains_visible_in_build_provenance(tmp_cfg, sample_model, monkeypatch):
    from sdd import site_build
    from sdd.export_site import export_site
    from test_export_site import prepare
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    before = json.loads((out / site_build.MANIFEST).read_text(encoding='utf-8'))
    digest = site_build.digest
    monkeypatch.setattr(site_build, 'digest', lambda path:
        'f' * 64 if path.name == 'design_response.py' else digest(path))
    export_site(tmp_cfg)
    after = json.loads((out / site_build.MANIFEST).read_text(encoding='utf-8'))
    assert before['outputs'] == after['outputs']
    assert before['engine']['design_response.py'] != after['engine']['design_response.py']
    assert before['build_id'] != after['build_id']


@pytest.mark.parametrize('runner', ['hermes', 'claude', 'opencode'])
@pytest.mark.parametrize('schema_mode', ['none', 'object'])
def test_checkpoint_execution_identity_keeps_legacy_fingerprint(generated, tmp_cfg, monkeypatch, runner, schema_mode):
    """Moving argv assembly must not invalidate existing unit checkpoint keys."""
    from sdd import cli_checkpoint, design_execution
    fixture = json.loads((Path(__file__).parent / 'fixtures' / 'cli-execution-141.json').read_text(encoding='utf-8'))
    tmp_cfg.agent.kind, tmp_cfg.agent.runner = 'cli', runner
    tmp_cfg.agent.model = 'fixture-model'
    tmp_cfg.agent.command = ['fixture-cli', 'subcommand']
    tmp_cfg.agent.args = ['--custom', '한글']
    tmp_cfg.raw.setdefault('review', {})['cli_checkpoint'] = True
    schema = None if schema_mode == 'none' else fixture['schema']
    monkeypatch.setattr(design_execution, 'response_schema', lambda *args: schema)
    captured = []

    class CapturedIdentity(Exception):
        pass

    def capture(cfg, identity):
        captured.append(identity['execution'])
        raise CapturedIdentity

    monkeypatch.setattr(cli_checkpoint, 'UnitStore', capture)
    section, model, _, _ = generated
    with pytest.raises(CapturedIdentity):
        design_execution._request_unit(tmp_cfg, model, object(), section, section['design_topics'][0],
                                       (None, 'fixed-system', 'fixed-policy'), False, None, {})
    assert len(captured) == 1
    assert cli_checkpoint.checksum(captured[0]) == fixture['fingerprints'][f'{runner}/{schema_mode}']
