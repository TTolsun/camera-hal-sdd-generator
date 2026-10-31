"""Navigation scope must not hide runtime claims or broken generated links."""
import hashlib

import pytest

from sdd.consistency import request, wire_payload
from sdd.facts.model import KnowledgeModel, Scenario
from sdd.next_steps import checked_footer


@pytest.fixture
def navigation_case(tmp_cfg, monkeypatch):
    revision = 'a' * 40
    model = KnowledgeModel(meta={'source_commit': revision})
    model.scenarios = {
        sid: Scenario(id=sid, title=title, entry=entry)
        for sid, title, entry in [('queue', 'Queue request', 'queueRequest'),
                                  ('complete', 'Complete request', 'completeRequest')]
    }
    sections = [dict(id='scenarios', kind='per-scenario')]
    monkeypatch.setattr(tmp_cfg, 'sections', lambda: sections)
    monkeypatch.setattr(tmp_cfg, 'scenarios', lambda: [dict(id=sid) for sid in model.scenarios])
    tmp_cfg.sdd_dir.mkdir(parents=True)
    (tmp_cfg.sdd_dir/'scenarios').mkdir()
    target = tmp_cfg.sdd_dir/'scenarios/complete.md'
    target.write_text(f'---\nsource_commit: {revision}\n---\n\n# Complete request\n\nCall completeRequest explicitly.', encoding='utf-8')
    meta = dict(section='scenarios', scenario_id='queue', source_commit=revision)
    footer = '다음 단계: [Complete request](complete.md)'
    body = '# Queue request\n\nThe caller must call completeRequest.\n\n' + footer + '\n'
    path = tmp_cfg.sdd_dir/'scenarios/queue.md'
    path.write_text('---\n'+'\n'.join(f'{k}: {v}' for k,v in meta.items())+'\n---\n\n'+body, encoding='utf-8')
    return tmp_cfg, model, meta, body, footer, target


def test_generated_footer_is_recorded_separately_but_runtime_claim_remains(navigation_case):
    cfg, model, meta, body, footer, target = navigation_case
    payload = request(cfg, model, dict(id='completion', primary='scenarios/queue.md',
                                      documents=['scenarios/queue.md'], match='completeRequest|Complete request'))
    assert [row['text'] for row in payload['claims'].values()] == ['The caller must call completeRequest.']
    navigation, = payload['excluded_navigation']
    assert navigation['text'] == footer+'\n'
    assert navigation['target'] == 'scenarios/complete.md'
    assert navigation['target_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert 'excluded_navigation' not in wire_payload(payload)


@pytest.mark.parametrize('change', [
    lambda b, f: b.replace(f, f+' Requests always complete immediately.'),
    lambda b, f: b.replace(f, f+'\nA caller must call completeRequest.'),
    lambda b, f: b.replace(f, f+'\n\nA caller must call completeRequest.'),
    lambda b, f: b.replace(f, 'See '+f),
    lambda b, f: b.replace(f, f.replace('Complete request', 'Always completes immediately')),
    lambda b, f: b.replace(f, '    '+f),
    lambda b, f: b.replace(f, '```text\n\n'+f),
    lambda b, f: b.replace(f, '~~~~text\n\n'+f),
    lambda b, f: b.replace(f, f.replace('complete.md', 'complete.md#guarantee')),
])
def test_mixed_custom_nonterminal_and_example_text_is_not_excluded(navigation_case, change):
    cfg, model, meta, body, footer, _ = navigation_case
    assert checked_footer(cfg, model, 'scenarios/queue.md', meta, change(body, footer)) is None


@pytest.mark.parametrize('change,error', [('missing', 'target missing'), ('commit', 'commit mismatch')])
def test_missing_or_stale_generated_target_fails_before_review(navigation_case, change, error):
    cfg, model, meta, body, _, target = navigation_case
    if change == 'missing':
        target.unlink()
    else:
        target.write_text(target.read_text().replace('a'*40, 'b'*40))
    with pytest.raises(ValueError, match=error):
        checked_footer(cfg, model, 'scenarios/queue.md', meta, body)


def test_custom_template_and_changed_target_title_stay_in_claim_scope(navigation_case):
    cfg, model, meta, body, _, target = navigation_case
    target.write_text(target.read_text().replace('# Complete request', '# Different contract'))
    assert checked_footer(cfg, model, 'scenarios/queue.md', meta, body) is None
    target.write_text(target.read_text().replace('# Different contract', '# Complete request'))
    (cfg.templates_dir/'page.md').write_text('Custom next-step layout')
    assert checked_footer(cfg, model, 'scenarios/queue.md', meta, body) is None


def test_configured_regular_document_uses_same_navigation_rule(navigation_case, monkeypatch):
    cfg, model, _, _, _, _ = navigation_case
    monkeypatch.setattr(cfg, 'sections', lambda: [dict(id='guide', output='guide.md',
        next=dict(title='Complete request', link='scenarios/complete.md'))])
    body = '# Guide\n\nA request requires explicit completion.\n\n다음 단계: [Complete request](scenarios/complete.md)\n'
    result = checked_footer(cfg, model, 'guide.md', dict(section='guide'), body)
    assert result['target'] == 'scenarios/complete.md'
