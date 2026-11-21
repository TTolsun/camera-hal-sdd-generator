"""Actual checkpoint paths preserve identical scoped manuscript bytes."""
import json
import hashlib

import pytest
import yaml

from test_generated_design import generated, cli_units
from sdd.document_metadata import split_frontmatter
from sdd.generate import Generator
from sdd.impact import ImpactReport


def add_scope(section):
    section['reader_profile'] = 'team'
    for row in section['design_requirements']:
        row['aspects'] = ['role', 'inputs', 'outputs', 'boundaries']
    section['reader_scope'] = dict(revision=1, change_reason='Fixed responsibility task.',
        tasks=[dict(id='responsibility', goal='Find the responsibilities.',
                    completion='Find answers and conditions.',
                    requirements=[r['id'] for r in section['design_requirements']])],
        optional=[], excluded=[], removed_requirements=[])


def test_configured_part_heading_is_presentation_not_an_uncited_paragraph(cli_units, tmp_cfg):
    section, model, save, _, state, agent = cli_units
    topic = section['design_topics'][0]
    topic['reuse_parts'] = True
    topic['parts'] = [{'id': 'conditions', 'question': topic['question'],
                       'sources': [source['id'] for source in topic['sources']], 'heading': 'Integration condition'}]
    save()
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    assert '### Integration condition\n\n' in path.read_text(encoding='utf-8')


def test_incremental_topic_reuses_proved_lead_on_addition_and_followup(cli_units, tmp_cfg, monkeypatch):
    from sdd.design_request import prepare_requests, reusable_prefixes
    from sdd.design_response import _validate_retained

    section, model, save, _, state, agent = cli_units
    topic = section['design_topics'][0]
    tid = topic['id']
    topic['parts'] = [{'id': 'lead', 'question': topic['question'],
                       'sources': [source['id'] for source in topic['sources']]}]
    save()
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    original = path.read_text(encoding='utf-8')
    before, _ = split_frontmatter(original)
    assert 'part_inputs' not in before['generated_design']

    source = {'id': 'limit', 'file': 'device.cpp', 'start': 'void bounded()', 'end': '}'}
    topic['sources'].append(source)
    topic['reuse_parts'] = True
    topic['parts'].append({'id': 'limit', 'question': 'Which extra guard limits capture?',
                           'sources': ['limit'], 'heading': 'Integration condition'})
    key = f"{section['id']}/{tid}/limit"
    def evidence(text):
        model.evidence[key] = {'selector': source, 'commit': model.meta['source_commit'], 'file': 'device.cpp',
                               'line': 30, 'end_line': 30, 'status': 'available', 'text': text,
                               'sha256': hashlib.sha256(text.encode()).hexdigest()}
    evidence('void bounded() { clampExposure(8); }')
    save()

    requests = []
    def answer(cfg, model, agent, section, unit, *args):
        requests.append(unit['_part_id'])
        return [{'text': '노출 시간은 가드의 제한을 받습니다.', 'quote': model.evidence[key]['text'],
                 'evidence': ['limit'], 'covers': topic['covers'], 'kind': 'behavior', 'part_id': 'limit'}], None
    monkeypatch.setattr('sdd.generated_design._request_unit', answer)
    report = ImpactReport('b' * 40, model.meta['source_commit'], sections={section['id']: ['new excerpt']})
    Generator(tmp_cfg, model, agent()).run(impact=report)
    assert requests == ['limit']
    first, _ = split_frontmatter(path.read_text(encoding='utf-8'))
    assert first['generated_design']['answers'][tid][:-1] == before['generated_design']['answers'][tid]
    assert 'part_inputs' in first['generated_design']

    evidence('void bounded() { clampExposure(9); }')
    save()
    Generator(tmp_cfg, model, agent()).run(impact=report)
    assert requests == ['limit', 'limit']
    current = path.read_text(encoding='utf-8')
    current_meta, _ = split_frontmatter(current)
    assert current_meta['generated_design']['answers'][tid][:-1] == before['generated_design']['answers'][tid]
    (tmp_cfg.style_dir/'README.md').write_text('Changed shared writing guide.', encoding='utf-8')
    plan = prepare_requests(tmp_cfg, model, section, current)
    assert reusable_prefixes(tmp_cfg, model, section, plan, {}, _validate_retained)[1] == {}


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


@pytest.mark.parametrize('changed_origin', [False, True])
def test_incremental_manuscript_reuse_checks_its_checkpoint_origins(cli_units, tmp_cfg, changed_origin):
    section, model, save, calls, state, agent = cli_units
    add_scope(section)
    save()
    report = ImpactReport('b' * 40, model.meta['source_commit'], sections={section['id']: ['source changed']})
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run(impact=report)
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run(impact=report)[0]
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    assert meta['generated_design']['checkpoint_units']
    if changed_origin:
        meta['generated_design']['checkpoint_units'][0]['receipts'][0] = 'wrong-origin.receipt.json'
        path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body, encoding='utf-8')
    before, completed = path.read_bytes(), list(calls)
    Generator(tmp_cfg, model, agent()).run(impact=report)
    assert calls == completed
    assert (path.read_bytes() == before) is not changed_origin
