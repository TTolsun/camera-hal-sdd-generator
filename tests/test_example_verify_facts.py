"""Public example preflight must distinguish Git source from generated files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from sdd.facts.model import ClassInfo, KnowledgeModel, Location


@pytest.mark.parametrize('defect', [None, 'untracked', 'dirty', 'evidence'])
def test_public_preflight_requires_tracked_clean_source_and_valid_source_only_topics(tmp_cfg, monkeypatch, defect):
    script = Path(__file__).resolve().parents[1]/'examples/libcamera/verify_facts.py'
    spec = importlib.util.spec_from_file_location('example_verify_facts', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_cfg.source_root
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    text = 'void work() { complete(); }\n'
    (source/'unit.cpp').write_text(text, encoding='utf-8')
    subprocess.run(['git', '-C', str(source), 'add', 'unit.cpp'], check=True)
    subprocess.run(['git', '-C', str(source), '-c', 'user.name=Fixture', '-c',
                    'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    selector = dict(id='work', file='unit.cpp', start='void work()', end='}')
    section = dict(id='source-only', title='소스 질문', kind='prose', design_generation='llm',
                   design_requirements=[dict(id='work', question='무엇을 호출합니까?')],
                   design_topics=[dict(id='work', title='호출', question='무엇을 호출합니까?',
                                       covers=['work'], sources=[selector])])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [
        dict(id='api', title='API', kind='prose', facts={'classes': ['libcamera::Camera']}), section]},
        allow_unicode=True), encoding='utf-8')
    names = ['Camera', 'CameraManager', 'Request', 'PipelineHandler']
    model = KnowledgeModel(meta={'source_commit': head}, classes={
        'libcamera::'+name: ClassInfo('libcamera::'+name, loc=Location('unit.cpp', 1)) for name in names},
        evidence={'source-only/work/work': dict(selector=selector, commit=head, file='unit.cpp',
            line=1, end_line=1, text=text.strip(), sha256=hashlib.sha256(text.strip().encode()).hexdigest(), status='available')})
    if defect == 'untracked':
        (source/'build').mkdir()
        (source/'build/generated.h').write_text('enum Generated {};\n', encoding='utf-8')
        model.classes['Generated'] = ClassInfo('Generated', loc=Location('build/generated.h', 1))
    elif defect == 'dirty':
        (source/'unit.cpp').write_text(text+'// changed after extraction\n', encoding='utf-8')
    elif defect == 'evidence':
        model.evidence['source-only/work/work']['sha256'] = '0'*64
    model.save(tmp_cfg.facts_path)
    monkeypatch.setattr(module, 'load', lambda _: tmp_cfg)
    monkeypatch.setattr(sys, 'argv', ['verify_facts', '--config', str(tmp_cfg.root/'sdd.yaml')])
    assert module.main() == (0 if defect is None else 1)
    report = json.loads((tmp_cfg.build_dir/'facts-verification.json').read_text(encoding='utf-8'))
    assert report['source_only_sections'] == ['source-only']
    if defect == 'untracked':
        assert report['invalid_locations'] == ['build/generated.h:1']
