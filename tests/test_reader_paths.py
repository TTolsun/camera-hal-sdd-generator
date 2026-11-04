"""Entrances retain canonical facts, uncertainty and publication rollback."""
import json

import pytest
import yaml

from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.site_build import verify_site
from test_generated_design import generated


@pytest.fixture
def paths(tmp_cfg, generated):
    section, model, save, agent = generated
    section['design_topics'][0]['parts'] = [dict(id='conclusion', question='종료 책임은?', sources=['stop'])]
    save()
    Generator(tmp_cfg, model, agent).run()
    ref = dict(section='device', topic='stop')
    claims = [dict(id='observed', title='확인한 사실', kind='fact', condition='공개 정적 소스입니다.',
                   sources=[{**ref, 'part': 'conclusion'}])]
    for cid in ['hypothesis', 'unmeasured', 'decision_request']:
        claim = dict(id=cid.replace('_', '-'), title=cid, kind=cid, text='아직 확인하지 않았습니다.',
                     condition='기기 실행은 별도입니다.', sources=[ref], needed_inputs=['실제 자료가 필요합니다.'])
        if cid == 'decision_request':
            claim['options'] = ['검증합니다.', '보류합니다.']
        claims.append(claim)
    from sdd.reader_paths import ASPECTS
    data = dict(schema=1, ready=True, scope='범위가 제한된 예제입니다.', limitations='사람 평가 전입니다.',
                required_inputs=['사내 입력이 필요합니다.'], claims=claims, roles=[
                    dict(id=rid, title=rid, questions=[dict(aspect=a, question=a, claims=[c['id'] for c in claims])
                        for a in sorted(aspects)]) for rid, aspects in ASPECTS.items()])
    tmp_cfg.raw.setdefault('site', {})['reader_paths'] = 'reader-paths.yaml'
    def write():
        (tmp_cfg.root/'reader-paths.yaml').write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    write()
    return data, write, section, model, save, agent


def test_roles_project_one_canonical_answer_with_distinct_questions(tmp_cfg, paths):
    data, _, section, _, _, agent = paths
    source = (tmp_cfg.sdd_dir/'device.md').read_bytes()
    calls = len(agent.calls)
    site = export_site(tmp_cfg)
    before = (site/'site-manifest.json').read_bytes()
    assert verify_site(site)['broken_links'] == 0
    for rid in ['work', 'decision']:
        page = (site/f'reader-{rid}.html').read_text(encoding='utf-8')
        assert agent.statement['text'].split('`stop()`')[1] in page
        assert 'device.html#종료-책임' in page or 'device.html#%EC' in page
        assert page.count('id="claim-observed"') == 1
        for label in ['가설', '미측정', '결정 요청', '사람 검토 전', '사내 입력']:
            assert label in page
    assert source == (tmp_cfg.sdd_dir/'device.md').read_bytes()
    assert len(agent.calls) == calls
    assert 'reader_paths' in json.loads(before)['inputs']
    export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes() == before


@pytest.mark.parametrize('mutation', ['missing-topic', 'missing-part', 'mixed-commit', 'no-role-question',
    'unmeasured-as-fact', 'authored-fact', 'incomplete-template', 'missing-source', 'missing-claim',
    'collision', 'no-shared-fact'])
def test_invalid_role_inputs_preserve_previous_site(tmp_cfg, paths, mutation):
    data, write, section, model, save, _ = paths
    site = export_site(tmp_cfg)
    before = {p.relative_to(site): p.read_bytes() for p in site.rglob('*') if p.is_file()}
    if mutation == 'missing-topic':
        data['claims'][0]['sources'][0]['topic'] = 'missing'
    elif mutation == 'missing-part':
        data['claims'][0]['sources'][0]['part'] = 'missing'
    elif mutation == 'mixed-commit':
        path = tmp_cfg.sdd_dir/'device.md'
        path.write_text(path.read_text(encoding='utf-8').replace('a'*40, 'b'*40), encoding='utf-8')
    elif mutation == 'no-role-question':
        data['roles'][0]['questions'].pop()
    elif mutation == 'unmeasured-as-fact':
        data['claims'][2]['kind'] = 'fact'
    elif mutation == 'authored-fact':
        data['claims'][0]['text'] = 'Unproven improvement'
    elif mutation == 'incomplete-template':
        data['ready'] = False
    elif mutation == 'missing-source':
        model.evidence.clear()
        save()
    elif mutation == 'missing-claim':
        data['roles'][0]['questions'][0]['claims'] = ['missing']
    elif mutation == 'collision':
        (tmp_cfg.sdd_dir/'reader-work.md').write_text('# Owned manuscript', encoding='utf-8')
    elif mutation == 'no-shared-fact':
        for q in data['roles'][1]['questions']:
            q['claims'].remove('observed')
    write()
    with pytest.raises((ValueError, RuntimeError)):
        export_site(tmp_cfg)
    assert {p.relative_to(site): p.read_bytes() for p in site.rglob('*') if p.is_file()} == before


def test_removed_setting_removes_only_owned_role_outputs(tmp_cfg, paths):
    site = export_site(tmp_cfg)
    tmp_cfg.raw['site'].pop('reader_paths')
    export_site(tmp_cfg)
    assert not (site/'reader-work.html').exists()
    assert (site/'device.html').is_file()


def test_injected_index_is_not_shown_as_an_approved_manuscript(tmp_cfg, paths):
    from sdd import approvals
    data, write, section, model, save, _ = paths
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    sections['sections'].append(dict(id='index', title='Home', kind='manual', output='index.md'))
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    text = '---\ngeneration_method: manual\nstatus: ok\n---\n# Original home\n\nApproved before new navigation.\n'
    (tmp_cfg.sdd_dir/'index.md').write_text(text, encoding='utf-8')
    ledger = approvals.load(tmp_cfg)
    approvals.approve_page(ledger, 'index.md', text, 'synthetic reviewer')
    approvals.save(tmp_cfg, ledger)
    site = export_site(tmp_cfg)
    assert '사람 검토 전' in (site/'index.html').read_text(encoding='utf-8')
    assert approvals.page_status(approvals.load(tmp_cfg), 'index.md', text) == 'approved'
    assert (tmp_cfg.sdd_dir/'index.md').read_text(encoding='utf-8') == text


def test_required_approval_does_not_skip_deterministic_role_metadata(tmp_cfg, paths):
    from sdd import approvals
    text = (tmp_cfg.sdd_dir/'device.md').read_text(encoding='utf-8')
    ledger = approvals.load(tmp_cfg)
    approvals.approve_page(ledger, 'device.md', text, 'synthetic reviewer')
    approvals.save(tmp_cfg, ledger)
    site = export_site(tmp_cfg)
    before = (site/'site-manifest.json').read_bytes()
    tmp_cfg.raw['site']['require_approval'] = True
    with pytest.raises(RuntimeError, match='역할별 판단'):
        export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes() == before
