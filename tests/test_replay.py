import json
from argparse import Namespace

import pytest

from sdd import replay as replay_module
from sdd.replay import PLACEHOLDER, manifest_delta, summary, translation_need


def test_manifest_delta_separates_preview_omissions_from_real_removals():
    baseline = dict(outputs={'a.html': '1', 'b.html': '2', 'gone.html': '3', 'item-visual-audit.json': '4'},
                    inputs={'facts': 'x', 'item_visual_reviews': 'r', 'configuration': 'c'})
    current = dict(outputs={'a.html': '1', 'b.html': '9', 'new.html': '5'},
                   inputs={'facts': 'y', 'item_visual_reviews': None, 'configuration': 'd'})
    delta = manifest_delta(baseline, current)
    assert delta['changed'] == ['b.html'] and delta['added'] == ['new.html']
    assert delta['removed'] == ['gone.html']
    assert delta['inputs_changed'] == ['facts']
    assert delta['preview_omitted'] == dict(outputs=['item-visual-audit.json'],
                                            inputs=['configuration', 'item_visual_reviews'])


def _report(**counts):
    report = dict(outputs=dict(changed=[], added=[], removed=[]),
                  translation=dict(enabled=True, model_required=counts.get('translation', 0), fixed_fill=2),
                  visual_reviews=dict(enabled=True, review_required=counts.get('visual', 0), exact=1, position_only=0,
                                      presentation_only=3, source_revision=0),
                  contract_audit=dict(enabled=True, fresh=counts.get('contract', 0), batches=40, fresh_input_chars=0))
    report['model_work_required'] = any(counts.values())
    return report


@pytest.mark.parametrize('counts', [dict(translation=1), dict(visual=590), dict(contract=40)])
def test_any_model_work_fails_the_replay_command(monkeypatch, counts, tmp_cfg):
    from sdd import cli
    monkeypatch.setattr(replay_module, 'replay', lambda cfg, baseline, out: _report(**counts))
    monkeypatch.setattr(cli, '_cfg', lambda args: tmp_cfg)
    assert cli.cmd_replay(Namespace(baseline='b', out='o')) == 2
    assert summary(_report(**counts))[-1] == 'model work required'


def test_no_model_work_passes_and_reports_each_cache(monkeypatch, tmp_cfg):
    from sdd import cli
    monkeypatch.setattr(replay_module, 'replay', lambda cfg, baseline, out: _report())
    monkeypatch.setattr(cli, '_cfg', lambda args: tmp_cfg)
    assert cli.cmd_replay(Namespace(baseline='b', out='o')) == 0
    lines = summary(_report())
    assert any(line.startswith('visual reviews: 0 need review') and 'presentation 3' in line for line in lines)
    assert any(line.startswith('contract audit: 0 of 40') for line in lines)


def test_translation_need_fills_fixed_labels_and_never_touches_the_configured_catalog(monkeypatch, tmp_cfg, tmp_path):
    catalog = tmp_cfg.root / 'english.json'
    original = dict(schema=1, strings={'기존 문장': 'Existing sentence.'})
    catalog.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = 'english.json'

    def prepare(cfg, destination):
        data = json.loads(destination.read_text(encoding='utf-8'))
        data['strings'].update({'발췌 범위: {{1}} ~ {{3}}': '', '새 설명 문장입니다.': ''})
        destination.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    monkeypatch.setattr('sdd.localization_cli.prepare_catalog', prepare)
    scratch = tmp_path / 'scratch.json'
    result = translation_need(tmp_cfg, scratch)
    assert result['fixed_fill'] == 1 and result['model_required'] == 1
    assert result['model_required_sample'] == ['새 설명 문장입니다.']
    filled = json.loads(scratch.read_text(encoding='utf-8'))['strings']
    assert filled['발췌 범위: {{1}} ~ {{3}}'] == 'Excerpt range: {{1}} to {{3}}'
    assert filled['새 설명 문장입니다.'] == PLACEHOLDER
    assert json.loads(catalog.read_text(encoding='utf-8')) == original


def test_replay_refuses_an_existing_output(tmp_cfg, tmp_path):
    (tmp_path / 'out').mkdir()
    with pytest.raises(ValueError, match='already exists'):
        replay_module.replay(tmp_cfg, tmp_path, tmp_path / 'out')


def test_baseline_catalog_is_used_only_when_it_built_the_baseline(tmp_cfg, tmp_path):
    import hashlib
    from sdd.replay import _published_catalog
    catalog = tmp_cfg.root / 'english.json'
    catalog.write_text('{"schema": 1, "strings": {}}', encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = 'english.json'
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    (baseline / 'site-manifest.json').write_text(json.dumps(dict(inputs=dict(english_catalog=digest))), encoding='utf-8')
    assert _published_catalog(tmp_cfg, baseline) == catalog
    catalog.write_text('{"schema": 1, "strings": {"새": ""}}', encoding='utf-8')
    assert _published_catalog(tmp_cfg, baseline) is None
