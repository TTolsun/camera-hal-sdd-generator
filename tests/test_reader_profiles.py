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

ROOT = Path(__file__).resolve().parents[1]


def test_non_libcamera_reader_profiles_generate_and_preserve_outputs_on_failure(tmp_cfg):
    # Use the committed mini HAL, not fabricated evidence or libcamera fixtures.
    tmp_cfg.raw["documentation"] = {"enabled": True}
    tmp_cfg.source_root = ROOT / 'examples/mini-hal'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    sections = yaml.safe_load((tmp_cfg.source_root / 'config/reader-sections.yaml').read_text(encoding='utf-8'))
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
    assert len(paths) == 2
    for path in paths:
        text = path.read_text(encoding='utf-8')
        assert 'status: ok' in text and 'source-bound-contract' in text
        assert text.count('#include "device/RequestManager.h"') == 1
        assert 'libcamera::' not in text
        assert '??? note "설계 질문과 검증 범위"' in text
    export_site(tmp_cfg)
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
    assert {s['reader_profile'] for s in profiles} == {'vendor', 'developer'}
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
