"""Trials retain effective inputs while keeping output away from live documents."""
import copy
from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from sdd.config import Config, load
from sdd.trial_workspace import clone_config, contained_path, reject_symlinks, validate_output, write_snapshot


def test_reparse_point_is_rejected_without_python312_junction_api(tmp_path, monkeypatch):
    from types import SimpleNamespace
    target = tmp_path/'reparse'
    target.mkdir()
    original = Path.lstat
    def reparse(path, *a, **kw):
        record = original(path, *a, **kw)
        return SimpleNamespace(st_mode=record.st_mode, st_file_attributes=0x400) if path == target else record
    monkeypatch.setattr(Path, 'lstat', reparse)
    monkeypatch.setattr(Path, 'is_junction', lambda self: False, raising=False)
    with pytest.raises(ValueError, match='symbolic links'):
        reject_symlinks(target/'new-trial')


def test_output_allows_new_build_trial_without_creating_it(tmp_cfg):
    out = tmp_cfg.build_dir / 'trials' / 'fresh'
    assert validate_output(tmp_cfg, out) == out.resolve()
    assert not out.exists()


def test_config_files_in_project_root_still_allow_a_build_trial(tmp_cfg):
    tmp_cfg.paths['config'] = tmp_cfg.root
    out = tmp_cfg.build_dir / 'trial'
    assert validate_output(tmp_cfg, out) == out.resolve()


@pytest.mark.parametrize('group,key', [('site', 'intro'), ('site', 'english_catalog'),
                                     ('site', 'mermaid_dir'), ('visuals', 'file')])
@pytest.mark.parametrize('absolute', [False, True])
def test_output_rejects_raw_asset_inputs_and_their_ancestors(tmp_cfg, group, key, absolute):
    asset = tmp_cfg.root / 'runtime-assets' / key / 'source'
    value = str(asset if absolute else asset.relative_to(tmp_cfg.root))
    tmp_cfg.raw[group] = {key: value}
    for out in (asset.parent, asset / 'trial'):
        with pytest.raises(ValueError, match='isolated'):
            validate_output(tmp_cfg, out)
        assert not out.exists()
    assert validate_output(tmp_cfg, tmp_cfg.build_dir / 'trial') == tmp_cfg.build_dir / 'trial'


def test_trial_cannot_be_nested_in_mermaid_assets_that_would_copy_it_recursively(tmp_cfg):
    assets = tmp_cfg.root / 'assets' / 'mermaid'
    assets.mkdir(parents=True)
    entry = assets / 'mermaid.esm.min.mjs'
    entry.write_bytes(b'preserved mermaid asset')
    tmp_cfg.raw['site'] = {'mermaid_dir': 'assets/mermaid/../mermaid'}
    out = assets / 'trial'
    with pytest.raises(ValueError, match='isolated'):
        validate_output(tmp_cfg, out)
    assert not out.exists()
    assert entry.read_bytes() == b'preserved mermaid asset'


@pytest.mark.parametrize('target', ['root', 'parent', 'source', 'source-child', 'facts', 'sdd',
                                   'diagrams', 'sections', 'prompts', 'templates', 'style'])
def test_output_rejects_operational_inputs(tmp_cfg, target):
    paths = dict(root=tmp_cfg.root, parent=tmp_cfg.root.parent, source=tmp_cfg.source_root,
                 **{'source-child': tmp_cfg.source_root / 'trial'}, facts=tmp_cfg.facts_dir,
                 sdd=tmp_cfg.sdd_dir, diagrams=tmp_cfg.diagrams_dir,
                 sections=tmp_cfg.sections_file, prompts=tmp_cfg.prompts_dir,
                 templates=tmp_cfg.templates_dir, style=tmp_cfg.style_dir)
    with pytest.raises(ValueError, match='isolated'):
        validate_output(tmp_cfg, paths[target])


def test_existing_output_and_overlap_with_previous_are_rejected(tmp_cfg):
    previous = tmp_cfg.root.parent / 'previous'
    previous.mkdir()
    previous.joinpath('record.json').write_text('preserve')
    for out in (previous, previous / 'nested', previous.parent):
        with pytest.raises(ValueError, match='isolated'):
            validate_output(tmp_cfg, out, previous=[previous])
    assert previous.joinpath('record.json').read_text() == 'preserve'


def test_symlink_components_are_rejected_before_resolve(tmp_cfg, monkeypatch):
    linked = tmp_cfg.root / 'linked'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == linked or original(p))
    with pytest.raises(ValueError, match='symbolic links'):
        validate_output(tmp_cfg, linked / 'trial')
    with pytest.raises(ValueError, match='symbolic links'):
        reject_symlinks(linked)


@pytest.mark.parametrize('relative', ['../outside.txt', 'nested/../../outside.txt'])
def test_contained_input_rejects_parent_traversal(tmp_path, relative):
    with pytest.raises(ValueError, match='relative path'):
        contained_path(tmp_path, relative)
    with pytest.raises(ValueError, match='relative path'):
        contained_path(tmp_path, tmp_path / 'absolute.txt')


def test_contained_input_rejects_nested_symlink(tmp_path, monkeypatch):
    nested = tmp_path / 'nested'
    nested.mkdir()
    linked = nested / 'response.txt'
    linked.write_text('contents')
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == linked or original(p))
    with pytest.raises(ValueError, match='symbolic links'):
        reject_symlinks(tmp_path, recursive=True)
    with pytest.raises(ValueError, match='symbolic links'):
        contained_path(tmp_path, 'nested/response.txt')


def test_clone_preserves_assets_and_nested_settings_without_mutating_original(tmp_cfg):
    cfg = tmp_cfg
    cfg.raw.update(site={'enabled': True, 'intro': 'intro.md', 'mermaid_dir': 'assets/mermaid',
                         'english_catalog': 'translations/en.json'}, visuals={'file': 'visuals.yaml'})
    cfg.paths['config'] = cfg.root / 'custom-config'
    before = copy.deepcopy(cfg)
    out = validate_output(cfg, cfg.build_dir / 'trial')
    trial = clone_config(cfg, out)
    assert cfg == before
    assert trial.root == out
    assert trial.sdd_dir == out / 'manuscripts'
    assert trial.diagrams_dir == trial.sdd_dir / 'diagrams'
    assert trial.facts_dir == out / 'facts'
    assert trial.source_root == cfg.source_root and trial.compile_commands == cfg.compile_commands
    assert trial.sections_file == cfg.sections_file
    assert trial.scenarios_file == cfg.scenarios_file
    assert trial.paths['glossary_file'] == cfg.config_dir / 'glossary.yaml'
    assert trial.prompts_dir == cfg.prompts_dir and trial.style_dir == cfg.style_dir
    for key in ('intro', 'mermaid_dir', 'english_catalog'):
        assert trial.raw['site'][key] == str((cfg.root / cfg.raw['site'][key]).resolve())
    assert trial.raw['visuals']['file'] == str(cfg.root / 'visuals.yaml')
    assert trial.raw['site']['enabled'] is False
    trial.agent.args.append('trial-only')
    trial.exclude.append('trial-only')
    assert cfg == before


def test_snapshot_roundtrip_uses_effective_config_and_preserves_exact_sections(tmp_cfg):
    cfg = tmp_cfg
    cfg.agent.kind, cfg.agent.runner, cfg.agent.model = 'cli', 'opencode', 'chosen/model'
    cfg.agent.command = ['runner.exe', '--mode', 'actual']
    cfg.agent.args = ['--config', '명시 설정']
    cfg.agent.allow_direct_api = False
    cfg.max_retries, cfg.require_citations, cfg.package_depth = 4, False, 3
    cfg.exclude, cfg.clang_uml_bin = ['third_party/**'], 'off'
    cfg.ndk_build = {'enabled': True, 'project_dir': str(cfg.source_root / 'project'), 'clang': 'clang++'}
    cfg.raw['agent'] = {'kind': 'ollama', 'model': 'stale/model'}
    cfg.raw['review'] = {'max_retries': 99, 'require_citations': True, 'custom_policy': 'preserve'}
    before = copy.deepcopy(cfg)
    out = validate_output(cfg, cfg.build_dir / 'snapshot-trial')
    out.mkdir(parents=True)
    section_bytes = b'# exact bytes\r\nsections: []\r\n'
    sections = out / 'sections.yaml'
    sections.write_bytes(section_bytes)
    trial = clone_config(cfg, out, sections_file=sections)
    snapshot = write_snapshot(trial, out / 'sdd.yaml')
    loaded = load(snapshot)
    for field in fields(Config):
        if field.name != 'raw':
            assert getattr(loaded, field.name) == getattr(trial, field.name), field.name
    assert loaded.sections_file.read_bytes() == section_bytes
    assert loaded.agent.label == 'cli/opencode/chosen/model'
    assert loaded.raw['review']['custom_policy'] == 'preserve'
    assert yaml.safe_load(snapshot.read_text(encoding='utf-8'))['agent']['args'] == cfg.agent.args
    assert cfg == before


def test_snapshot_must_stay_with_trial_root_for_build_directory_roundtrip(tmp_cfg):
    trial = clone_config(tmp_cfg, tmp_cfg.build_dir / 'trial')
    with pytest.raises(ValueError, match='trial root'):
        write_snapshot(trial, tmp_cfg.root / 'different-root.yaml')


def test_snapshot_handles_optional_null_yaml_mappings(tmp_cfg):
    for key in ('source', 'tools', 'review', 'facts', 'site', 'visuals'):
        tmp_cfg.raw[key] = None
    out = validate_output(tmp_cfg, tmp_cfg.build_dir / 'null-mappings')
    out.mkdir(parents=True)
    trial = clone_config(tmp_cfg, out)
    reloaded = load(write_snapshot(trial, out / 'sdd.yaml'))
    assert reloaded.agent == trial.agent
    assert reloaded.source_root == trial.source_root
    assert reloaded.raw['site']['enabled'] is False
