"""Actual checkpoint paths preserve identical scoped manuscript bytes."""
import json

import pytest
import yaml

from test_generated_design import generated, cli_units
from sdd.document_metadata import split_frontmatter
from sdd.generate import Generator


def add_scope(section):
    section['reader_profile'] = 'team'
    for row in section['design_requirements']:
        row['aspects'] = ['role', 'inputs', 'outputs', 'boundaries']
    section['reader_scope'] = dict(revision=1, change_reason='Fixed responsibility task.',
        tasks=[dict(id='responsibility', goal='Find the responsibilities.',
                    completion='Find answers and conditions.',
                    requirements=[r['id'] for r in section['design_requirements']])],
        optional=[], excluded=[], removed_requirements=[])


def test_plain_generate_retains_bytes_after_all_cli_units_revalidated(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    add_scope(section); save(); state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    original, completed = path.read_bytes(), list(calls)
    # No impact object: this follows the ordinary CLI generate path, so units
    # come from receipt-bound checkpoints rather than prior-manuscript reuse.
    Generator(tmp_cfg, model, agent()).run()
    assert calls == completed
    assert path.read_bytes() == original
    reports = [json.loads(p.read_text(encoding='utf-8'))
               for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert any(all(v.startswith('checkpoint-') for v in r['documents'][0]['units'].values()) for r in reports)


@pytest.mark.parametrize('change', ['heading', 'policy'])
def test_changed_display_or_validation_policy_is_not_hidden_by_preservation(cli_units, tmp_cfg, monkeypatch, change):
    section, model, save, calls, state, agent = cli_units
    add_scope(section); save(); state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    original, completed = path.read_bytes(), list(calls)
    if change == 'heading':
        section['design_topics'][0]['title'] += ' 새 제목'
        save()
    else:
        monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'current': 'changed-check'})
    Generator(tmp_cfg, model, agent()).run()
    assert calls == completed
    assert path.read_bytes() != original
    if change == 'heading':
        assert '새 제목' in path.read_text(encoding='utf-8')
    else:
        meta, _ = split_frontmatter(path.read_text(encoding='utf-8'))
        assert meta['generated_design']['validation_policy'] == {'current': 'changed-check'}


def test_changed_old_receipt_binding_is_not_discarded_as_a_run_annotation(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    add_scope(section); save()
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run()
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    assert meta['generated_design']['checkpoint_units']
    meta['generated_design']['checkpoint_units'][0]['receipts'][0] = 'wrong-origin.receipt.json'
    path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body, encoding='utf-8')
    before, completed = path.read_bytes(), list(calls)
    Generator(tmp_cfg, model, agent()).run()
    assert calls == completed and path.read_bytes() != before
    assert 'wrong-origin.receipt.json' not in path.read_text(encoding='utf-8')
