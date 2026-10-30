import copy
import subprocess
from pathlib import Path

import pytest
import yaml

from sdd.contract_schema import configuration_errors
from sdd.evidence import collect
from sdd.export_site import export_site
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator
from sdd.reader_profiles import PROFILES


def split_family():
    sections = [dict(id='entry', output='entry.md', reader_profile='vendor', reader_family='guide',
                     design_requirements=[dict(id=k, aspects=[k]) for k in ['inputs', 'ownership']]),
                dict(id='detail', output='detail.md', reader_profile='vendor', reader_family='guide',
                     design_requirements=[dict(id=k, aspects=[k]) for k in ['completion', 'failure', 'verification']])]
    features = [dict(id='guide', primary='entry.md', sections=['detail'], reader_profile='vendor')]
    return sections, features


def test_split_reader_family_keeps_every_original_required_aspect_and_dense_guard():
    from sdd.reader_profiles import family_errors, profile_errors
    sections, features = split_family()
    assert family_errors(sections, features) == []
    assert all(configuration_errors(s) == [] for s in sections)
    sections[0]['design_topics'] = [dict(id='long', statements=[dict(text='문장입니다. ' * 8)])]
    assert any('4문장' in error for error in profile_errors(sections[0]))


def test_family_membership_revalidates_the_guide_without_replacing_identical_drafts():
    from sdd.design_reuse import topic_inputs
    from sdd.evidence import fingerprint
    section = dict(id='guide', reader_profile='vendor', design_topics=[dict(id='one', covers=['one'])],
                   design_requirements=[dict(id='one', aspects=['inputs'])])
    model = KnowledgeModel()
    before = topic_inputs(model, section, 'actual drafting policy')
    whole_before = fingerprint(model, section)
    section['reader_family'] = 'split-guide'
    assert topic_inputs(model, section, 'actual drafting policy') == before
    assert fingerprint(model, section) != whole_before
    assert topic_inputs(model, section, 'changed actual drafting policy') != before


@pytest.mark.parametrize('change', ['aspect', 'member', 'declaration', 'profile', 'orphan', 'disabled'])
def test_split_reader_family_cannot_skip_coverage_or_its_publication_gate(change):
    from sdd.reader_profiles import family_errors
    sections, features = split_family()
    if change == 'aspect': sections[1]['design_requirements'].pop()
    elif change == 'member': features[0]['sections'] = ['missing']
    elif change == 'declaration': sections[1].pop('reader_family')
    elif change == 'profile': sections[1]['reader_profile'] = 'developer'
    elif change == 'orphan': sections[1]['reader_family'] = 'missing'
    assert family_errors(sections, features, enabled=change != 'disabled')


def test_invalid_reader_family_fails_before_git_calls_and_preserves_old_outputs(tmp_cfg, monkeypatch):
    sections, features = split_family()
    sections[1]['design_requirements'].pop()
    tmp_cfg.sections_file.write_text(yaml.safe_dump(dict(sections=sections)), encoding='utf-8')
    tmp_cfg.raw['documentation'] = dict(enabled=True, features=features)
    model = KnowledgeModel(evidence={'old': {'text': 'preserved'}})
    target = tmp_cfg.sdd_dir/'entry.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('previous manuscript', encoding='utf-8')
    monkeypatch.setattr('sdd.source_git.file_at', lambda *a, **kw: pytest.fail('No Git reads for invalid family'))
    with pytest.raises(ValueError, match='verification'):
        collect(tmp_cfg, model)
    with pytest.raises(ValueError, match='verification'):
        Generator(tmp_cfg, model, object())
    assert model.evidence == {'old': {'text': 'preserved'}}
    assert target.read_text(encoding='utf-8') == 'previous manuscript'


def test_portable_split_family_builds_and_missing_detail_blocks_existing_site(tmp_cfg):
    tmp_cfg.source_root = ROOT/'examples/mini-hal'
    config = yaml.safe_load((tmp_cfg.source_root/'config/reader-sections.yaml').read_text(encoding='utf-8'))
    original = next(s for s in config['sections'] if s.get('reader_profile') == 'vendor')
    detail = copy.deepcopy(original)
    detail.update(id='vendor-detail', output='vendor-detail.md', title='상세 계약')
    moved = {t['id'] for t in original['design_topics'][len(original['design_topics'])//2:]}
    for section, keep in [(original, False), (detail, True)]:
        section['reader_family'] = 'portable-guide'
        section['design_topics'] = [t for t in section['design_topics'] if (t['id'] in moved) == keep]
        covers = {r for t in section['design_topics'] for r in t.get('covers', [])}
        covers.update(r for t in section['design_topics'] for st in t.get('statements', []) for r in st.get('covers', []))
        section['design_requirements'] = [r for r in section['design_requirements'] if r['id'] in covers]
        section['routes'] = []
    config['sections'].append(detail)
    tmp_cfg.raw['documentation'] = dict(enabled=True, features=[dict(id='portable-guide',
        primary=original['output'], sections=['vendor-detail'], reader_profile='vendor')])
    tmp_cfg.sections_file.write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
    tmp_cfg.scenarios_file.write_text('scenarios: []\n', encoding='utf-8')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    model = KnowledgeModel(meta={'source_commit': commit})
    collect(tmp_cfg, model)
    model.save(tmp_cfg.facts_path)
    class NoModel:
        def chat(self, *a, **kw): pytest.fail('Source-bound mini HAL fixture needs no model')
    Generator(tmp_cfg, model, NoModel()).run()
    site = export_site(tmp_cfg)
    manifest = (site/'site-manifest.json').read_bytes()
    (tmp_cfg.sdd_dir/'vendor-detail.md').unlink()
    with pytest.raises(RuntimeError, match='lifecycle'):
        export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes() == manifest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('navigation', ['mini-hal', 'inhouse-template'])
def test_non_libcamera_reader_profiles_generate_and_preserve_outputs_on_failure(tmp_cfg, navigation):
    # Use the committed mini HAL, not fabricated evidence or libcamera fixtures.
    tmp_cfg.raw["documentation"] = {"enabled": True}
    tmp_cfg.source_root = ROOT / 'examples/mini-hal'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    sections = yaml.safe_load((tmp_cfg.source_root / 'config/reader-sections.yaml').read_text(encoding='utf-8'))
    if navigation == 'inhouse-template':
        template = yaml.safe_load((ROOT / 'examples/inhouse-template/config/sections.yaml').read_text(encoding='utf-8'))
        by_profile = {s['reader_profile']: s for s in template['sections'] if s.get('reader_profile')}
        for section in sections['sections']:
            source = by_profile[section['reader_profile']]
            section.update({k: source[k] for k in ('group', 'nav_section')})
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    tmp_cfg.scenarios_file.write_text('scenarios: []\n', encoding='utf-8')
    model = KnowledgeModel(meta={'source_commit': commit})
    collect(tmp_cfg, model)
    assert all(r['status'] == 'available' for r in model.evidence.values())
    model.save(tmp_cfg.facts_path)
    class NoModel:
        def chat(self, *a, **kw):
            pytest.fail('Evidence-bound contracts must work with any model provider, including none')
    paths = Generator(tmp_cfg, model, NoModel()).run()
    assert len(paths) == 4
    for path in paths:
        text = path.read_text(encoding='utf-8')
        assert 'status: ok' in text and 'source-bound-contract' in text
        assert text.count('#include "device/RequestManager.h"') == 1
        assert 'libcamera::' not in text
        assert '??? note "설계 질문과 검증 범위"' in text
    site = export_site(tmp_cfg)
    from sdd.site_build import verify_site
    assert verify_site(site)['broken_links'] == 0
    page = (site / 'vendor-contract.html').read_text(encoding='utf-8')
    assert '<summary>도입 판단</summary>' in page
    assert '<summary>연동 구현</summary>' in page
    assert '<summary>구조 이해</summary>' in page
    assert page.count('<details class="nav-section" data-nav-id=') == 3
    # Menu grouping reuses the public renderer with unrelated HAL contracts.
    assert page.index('vendor-assurance.html') < page.index('vendor-contract.html')
    manifest_before = (site / 'site-manifest.json').read_bytes()
    export_site(tmp_cfg)
    assert (site / 'site-manifest.json').read_bytes() == manifest_before
    before = {p: p.read_bytes() for p in paths}
    manifest = tmp_cfg.build_dir / 'site/site-manifest.json'
    old_manifest = manifest.read_bytes()
    sections['sections'][1]['design_topics'][0]['statements'] = []
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='設計|설계'):
        Generator(tmp_cfg, model, NoModel()).run()
    assert before == {p: p.read_bytes() for p in paths}
    with pytest.raises(ValueError):
        export_site(tmp_cfg)
    assert manifest.read_bytes() == old_manifest


@pytest.mark.parametrize('role', list(PROFILES))
def test_profile_requires_each_reader_question(role):
    sec = {'reader_profile': role, 'design_requirements': [dict(id=k, aspects=[k]) for k in PROFILES[role]]}
    assert configuration_errors(sec) == []
    for i, key in enumerate(PROFILES[role]):
        missing = copy.deepcopy(sec)
        missing['design_requirements'][i]['aspects'] = []
        assert any(role + '/' + key in e for e in configuration_errors(missing))


def test_inhouse_template_cannot_silently_publish_empty_contracts(tmp_cfg):
    from sdd.design_contracts import audit
    sections = yaml.safe_load((ROOT / 'examples/inhouse-template/config/sections.yaml').read_text(encoding='utf-8'))['sections']
    profiles = [s for s in sections if s.get('reader_profile')]
    assert {s['reader_profile'] for s in profiles} == {'vendor-overview', 'vendor', 'vendor-assurance', 'developer', 'team'}
    for sec in profiles:
        assert configuration_errors(sec) == []
        assert audit(KnowledgeModel(), sec)['status'] == 'incomplete'


def test_reader_profile_rejects_dense_prose_but_preserves_structured_detail():
    section = yaml.safe_load((ROOT / 'examples/mini-hal/config/reader-sections.yaml').read_text(encoding='utf-8'))['sections'][0]
    answer = section['design_topics'][0]['statements'][0]
    answer['text'] = '조건을 확인합니다. ' * 5
    assert any('4문장' in e for e in configuration_errors(section))
    answer['text'] = '\n\n'.join(['조건을 확인합니다. ' * 3, '예외를 확인합니다. ' * 2])
    assert not configuration_errors(section)
    answer['text'] = '| 조건 | 설명 |\n|---|---|\n' + '| 상태 | 조건과 예외를 확인합니다. |\n' * 30
    assert not configuration_errors(section)


def test_developer_rejects_architecture_only_question_set():
    section = {'reader_profile': 'developer', 'design_requirements': [
        dict(id=k, aspects=[k]) for k in PROFILES['architecture']]}
    assert any('developer/entry' in e for e in configuration_errors(section))
    section['reader_profile'] = 'architecture'
    assert configuration_errors(section) == []  # Saved legacy configs remain supported.


def test_vendor_overview_rejects_implementation_only_contract():
    section = {'reader_profile': 'vendor-overview', 'design_requirements': [
        dict(id=k, aspects=[k]) for k in PROFILES['vendor']]}
    assert configuration_errors(section)
    section['reader_profile'] = 'vendor'
    assert configuration_errors(section) == []  # Detail pages keep their contract.


def test_public_and_portable_vendor_entry_pages_require_adoption_answers():
    for filename in ('libcamera/config/sections.yaml', 'inhouse-template/config/sections.yaml',
                     'mini-hal/config/reader-sections.yaml'):
        sections = yaml.safe_load((ROOT / 'examples' / filename).read_text(encoding='utf-8'))['sections']
        entry = next(s for s in sections if s.get('reader_profile') == 'vendor-overview')
        assert configuration_errors(entry) == []
        assert {'capabilities', 'benefits'} <= {
            r['id'] for r in entry['design_requirements']}
        for profile in ('vendor', 'vendor-assurance'):
            assert not configuration_errors(next(s for s in sections if s.get('reader_profile') == profile))


def test_B4_team_프로필은_역할_입력_출력_경계_질문을_요구한다():
    from sdd.reader_profiles import PROFILES, profile_errors
    assert set(PROFILES['team']) == {'role', 'inputs', 'outputs', 'boundaries'}
    section = {'reader_profile': 'team', 'design_requirements': [
        {'id': key, 'question': q, 'aspects': [key]} for key, q in PROFILES['team'].items()]}
    assert profile_errors(section) == []
    section['design_requirements'].pop()
    assert any('team/boundaries' in e for e in profile_errors(section))
