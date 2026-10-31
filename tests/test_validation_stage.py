"""Stage isolation is about checked bytes, not inheriting a previous pass."""
import copy
import json

import pytest

from sdd.validation_stage import InputChanged, current, load_json, load_yaml, read_text, stage


def test_identical_bytes_are_parsed_once_and_mutable_results_are_private(tmp_cfg, monkeypatch):
    import yaml
    original = yaml.safe_load
    calls = []
    monkeypatch.setattr(yaml, 'safe_load', lambda raw: (calls.append(raw), original(raw))[1])
    with stage() as inputs:
        for _ in range(24):
            sections = tmp_cfg.sections()
            sections[0]['title'] = 'caller mutation'
        assert tmp_cfg.sections()[0]['title'] != 'caller mutation'
        assert len(calls) == 2  # sections and scenarios; independent of document count
        assert inputs.parses == {'yaml': 2}
    assert current() is None
    with stage():
        tmp_cfg.sections()
    assert len(calls) == 4


def test_stage_between_changes_refresh_and_midstage_edits_fail(tmp_path):
    path = tmp_path/'input.yaml'
    path.write_text('value: first', encoding='utf-8')
    with stage():
        assert load_yaml(path)['value'] == 'first'
    path.write_text('value: second', encoding='utf-8')
    with pytest.raises(InputChanged, match='during validation'):
        with stage():
            assert load_yaml(path)['value'] == 'second'
            path.write_text('value: third', encoding='utf-8')
            assert load_yaml(path)['value'] == 'second'
    with stage():
        assert load_yaml(path)['value'] == 'third'


def test_missing_input_becoming_present_is_a_change(tmp_path):
    path = tmp_path/'override.yaml'
    with pytest.raises(InputChanged):
        with stage():
            assert load_yaml(path, optional=True) == {}
            path.write_text('value: new', encoding='utf-8')


def test_midstage_edit_cannot_hide_by_restoring_original_bytes(tmp_path):
    path = tmp_path/'input.yaml'
    path.write_text('value: original', encoding='utf-8')
    with pytest.raises(InputChanged):
        with stage():
            assert load_yaml(path)['value'] == 'original'
            path.write_text('value: changed', encoding='utf-8')
            path.write_text('value: original', encoding='utf-8')


def test_frontmatter_is_reused_without_sharing_mutations():
    from sdd.document_metadata import split_frontmatter
    text = '---\nsource_commit: fixed\n---\n\nBody'
    with stage() as inputs:
        a, body = split_frontmatter(text)
        a['source_commit'] = 'changed'
        assert split_frontmatter(text) == ({'source_commit': 'fixed'}, body)
        assert inputs.parses['yaml'] == 1


def test_profile_payload_is_constructed_once_but_changed_sections_are_distinct(tmp_cfg, sample_model, monkeypatch):
    from sdd import consistency
    from dataclasses import replace
    calls = []
    monkeypatch.setattr(consistency, '_request', lambda cfg, model, group: (calls.append(group), {'claims': {}})[1])
    review = replace(tmp_cfg, agent=copy.deepcopy(tmp_cfg.agent))
    review.agent.model = 'different-allowed-model'
    group = dict(id='one')
    with stage():
        assert consistency.request(tmp_cfg, sample_model, group) == consistency.request(review, sample_model, group)
        assert len(calls) == 1
        consistency.request(review, sample_model, dict(id='two'))
        assert len(calls) == 2


def test_memory_model_and_policy_change_are_checked(tmp_cfg, sample_model):
    with pytest.raises(InputChanged, match='In-memory'):
        with stage() as inputs:
            inputs.pin(tmp_cfg, sample_model)
            sample_model.meta['source_commit'] = 'other'
    with pytest.raises(InputChanged, match='during validation'):
        with stage() as inputs:
            inputs.pin(tmp_cfg)
            (tmp_cfg.style_dir/'README.md').write_text('changed policy', encoding='utf-8')


def test_json_and_text_share_original_bytes(tmp_path):
    path = tmp_path/'catalog.json'
    path.write_text('{"strings": {"key": "value"}}', encoding='utf-8')
    with stage() as inputs:
        for _ in range(10):
            assert load_json(path)['strings']['key'] == 'value'
            assert json.loads(read_text(path)) == load_json(path)
        assert inputs.parses == {'json': 1}


@pytest.mark.parametrize('loader', [load_json, load_yaml])
def test_input_cache_preserves_the_utf8_only_input_contract(tmp_path, loader):
    path = tmp_path/'input'
    path.write_bytes('{"value": 1}'.encode('utf-16'))
    with pytest.raises(UnicodeError):
        with stage():
            loader(path)


def test_failed_stage_does_not_replace_previous_site(tmp_cfg, tmp_path):
    from sdd.site_build import build_site
    out = tmp_path/'site'
    out.mkdir()
    sentinel = out/'keep.txt'
    sentinel.write_text('previous valid output', encoding='utf-8')
    def render(cfg, target, mermaid):
        (target/'index.html').write_text('<p>valid</p>', encoding='utf-8')
        cfg.sections_file.write_text('sections: []', encoding='utf-8')
    with pytest.raises(InputChanged):
        build_site(tmp_cfg, out, render, None)
    assert sentinel.read_text(encoding='utf-8') == 'previous valid output'
    assert not (out/'index.html').exists()


def test_source_file_changes_during_a_stage_are_rejected(tmp_cfg, sample_model):
    path = tmp_cfg.source_root/'device.cpp'
    path.write_text('original source', encoding='utf-8')
    sample_model.evidence['window'] = dict(file='device.cpp', status='available')
    with pytest.raises(InputChanged, match='during validation'):
        with stage() as inputs:
            inputs.pin(tmp_cfg, sample_model)
            path.write_text('changed source', encoding='utf-8')


def test_receipt_input_changed_after_it_was_checked_is_rejected(tmp_path):
    import hashlib
    from sdd.call_records import canonical_request_hash, load_record
    request = dict(system='source only', user='question', response_schema=None)
    (tmp_path/'001.request.json').write_text(json.dumps(request), encoding='utf-8')
    response = tmp_path/'001.response.txt'
    response.write_text('completed original', encoding='utf-8')
    receipt = tmp_path/'001.receipt.json'
    receipt.write_text(json.dumps(dict(request_sha256=canonical_request_hash(request),
        response_sha256=hashlib.sha256(response.read_bytes()).hexdigest())), encoding='utf-8')
    with pytest.raises(InputChanged, match='during validation'):
        with stage():
            assert load_record(receipt, root=tmp_path).raw == 'completed original'
            response.write_text('changed after check', encoding='utf-8')


def test_input_change_during_copy_rolls_back_all_owned_site_bytes(tmp_cfg, tmp_path, monkeypatch):
    import shutil
    from sdd.site_build import build_site
    out = tmp_path/'site'
    def render(cfg, target, mermaid):
        (target/'index.html').write_text('<p>original</p>', encoding='utf-8')
    build_site(tmp_cfg, out, render, None)
    (out/'CNAME').write_text('preserved.example', encoding='utf-8')
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    def changed(cfg, target, mermaid):
        (target/'index.html').write_text('<p>new</p>', encoding='utf-8')
        (target/'new.html').write_text('<p>new page</p>', encoding='utf-8')
    original = shutil.copyfile
    def copying(source, destination, *args, **kwargs):
        result = original(source, destination, *args, **kwargs)
        tmp_cfg.sections_file.write_text('sections: []', encoding='utf-8')
        return result
    monkeypatch.setattr('sdd.site_build.shutil.copyfile', copying)
    with pytest.raises(InputChanged, match='during validation'):
        build_site(tmp_cfg, out, changed, None)
    after = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    assert after == before


def test_translation_checks_inputs_before_replacing_existing_catalog(tmp_cfg, monkeypatch):
    from sdd.facts.model import KnowledgeModel
    from sdd.localization_cli import prepare_catalog
    KnowledgeModel(meta={'source_commit': 'a'*40}).save(tmp_cfg.facts_path)
    destination = tmp_cfg.root/'english.json'
    original = b'{"strings": {"old": "original"}}'
    destination.write_bytes(original)
    def render(cfg, out, **kwargs):
        (out/'index.html').write_text('<p>설명입니다.</p>', encoding='utf-8')
        (out/'assets').mkdir()
        (out/'assets/search.json').write_text('[]', encoding='utf-8')
        return out
    def translate(cfg, catalog, agent):
        cfg.sections_file.write_text('sections: []', encoding='utf-8')
        return catalog
    monkeypatch.setattr('sdd.export_site._render_site', render)
    monkeypatch.setattr('sdd.translation.translate_missing', translate)
    with pytest.raises(InputChanged):
        prepare_catalog(tmp_cfg, destination, translate=True)
    assert destination.read_bytes() == original
