import copy
import json
import subprocess

import pytest
import yaml

from sdd.cli import main
from sdd.impact_review import review_markdown
from sdd.facts.model import ClassInfo, FunctionInfo, KnowledgeModel, Location, Method
from sdd.impact import ImpactReport, compute
from sdd.source_git import changed_files


def sections(cfg, values):
    cfg.sections_file.write_text(yaml.safe_dump({'sections': values}), encoding='utf-8')


def test_watch_hit_does_not_hide_new_class_outside_document_scope(tmp_cfg):
    sections(tmp_cfg, [{'id': 'ipa', 'watch': ['src/**'], 'facts': {'classes': ['Manager']}}])
    model = KnowledgeModel(classes={'Lsc': ClassInfo('Lsc', Location('src/lsc.h', 8))})
    report = compute(tmp_cfg, model, ['src/lsc.h'], 'a', 'b')
    assert 'ipa' in report.sections
    assert report.coverage['status'] == 'needs-review'
    assert report.coverage['findings'][0]['name'] == 'Lsc'
    assert report.coverage['files'][0]['watch_sections'] == ['ipa']
    assert 'Lsc' in review_markdown(report)
    path = tmp_cfg.build_dir / 'impact.json'
    report.save(path)
    assert ImpactReport.load(path) == report


def test_adding_matching_section_resolves_scope_gap_for_method_definition(tmp_cfg):
    model = KnowledgeModel(classes={'hal::Lsc': ClassInfo('hal::Lsc', Location('lsc.h', 8),
        methods=[Method('run', Location('lsc.h', 9), def_loc=Location('lsc.cpp', 4))])})
    sections(tmp_cfg, [{'id': 'lsc', 'facts': {'classes': ['Lsc']}}])
    report = compute(tmp_cfg, model, ['lsc.cpp'], 'a', 'b')
    assert 'lsc' in report.sections
    assert report.coverage['findings'] == []
    assert report.coverage['entities'][0]['sections'] == ['lsc']
    assert report.coverage['entities'][0]['evidence']['head'] == ['lsc.cpp:4']


def test_covered_class_does_not_mask_uncovered_function_in_same_file(tmp_cfg):
    sections(tmp_cfg, [{'id': 'api', 'facts': {'classes': ['Device']}, 'watch': ['*.cpp']}])
    model = KnowledgeModel(classes={'Device': ClassInfo('Device', Location('api.cpp', 1))},
                           functions={'hal::open': FunctionInfo('hal::open', Location('api.cpp', 20))})
    report = compute(tmp_cfg, model, ['api.cpp'], 'a', 'b')
    assert [f['name'] for f in report.coverage['findings']] == ['hal::open']
    sections(tmp_cfg, [{'id': 'api', 'facts': {'classes': ['Device'], 'functions': ['open']}, 'watch': ['*.cpp']}])
    assert compute(tmp_cfg, model, ['api.cpp'], 'a', 'b').coverage['findings'] == []


def test_deleted_entity_in_surviving_file_is_detected_with_baseline(tmp_cfg):
    sections(tmp_cfg, [{'id': 'api', 'facts': {'classes': ['Kept']}, 'watch': ['*.h']}])
    head = KnowledgeModel(classes={'Kept': ClassInfo('Kept', Location('api.h', 1))})
    base = copy.deepcopy(head)
    base.classes['Removed'] = ClassInfo('Removed', Location('api.h', 20))
    report = compute(tmp_cfg, head, ['api.h'], 'a', 'b', base)
    assert [f['name'] for f in report.coverage['findings']] == ['Removed']
    assert report.coverage['baseline_available']
    without = compute(tmp_cfg, head, ['api.h'], 'a', 'b')
    assert not without.coverage['baseline_available']
    assert '--base-facts' in review_markdown(without)


def test_build_unparsed_deleted_files_and_manual_evidence_remain_reviewable(tmp_cfg):
    sections(tmp_cfg, [{'id': 'manual', 'kind': 'manual', 'output': 'notes.md', 'watch': ['**']}])
    tmp_cfg.sdd_dir.mkdir()
    (tmp_cfg.sdd_dir / 'notes.md').write_text('---\nevidence_files: [Android.mk]\n---\n', encoding='utf-8')
    tmp_cfg.exclude = ['vendor/**']
    report = compute(tmp_cfg, KnowledgeModel(), ['Android.mk', 'gone.cpp', 'unparsed.cpp', 'vendor/lib.cpp'], 'a', 'b')
    assert len(report.coverage['findings']) == 3
    assert report.coverage['ignored_files'] == ['vendor/lib.cpp']
    assert report.coverage['files'][0]['manual_review_sections'] == ['manual']
    assert all(f['reason'] == 'no-extracted-entity' for f in report.coverage['findings'])


def test_package_summary_or_manual_class_selector_is_not_class_coverage(tmp_cfg):
    sections(tmp_cfg, [{'id': 'summary', 'facts': {'packages': ['*']}},
                      {'id': 'manual', 'kind': 'manual', 'facts': {'classes': ['*']}}])
    model = KnowledgeModel(classes={'New': ClassInfo('New', Location('new.h', 1))})
    assert compute(tmp_cfg, model, ['new.h'], 'a', 'b').coverage['findings']


def test_changed_mapped_function_schedules_its_section(tmp_cfg):
    sections(tmp_cfg, [{'id': 'api', 'facts': {'functions': ['open']}}])
    model = KnowledgeModel(functions={'open': FunctionInfo('open', Location('api.cpp', 1))})
    report = compute(tmp_cfg, model, ['api.cpp'], 'a', 'b')
    assert report.sections == {'api': ['함수 변경: open']}
    assert report.coverage['findings'] == []


def test_mapped_function_without_regeneration_rule_requires_review(tmp_cfg):
    sections(tmp_cfg, [{'id': 'api', 'facts': {'functions': ['open'], 'impact_functions': []}}])
    model = KnowledgeModel(functions={'open': FunctionInfo('open', Location('api.cpp', 1))})
    report = compute(tmp_cfg, model, ['api.cpp'], 'a', 'b')
    assert report.coverage['findings'][0]['reason'] == 'document-not-scheduled'
    assert report.coverage['entities'][0]['sections'] == ['api']


def test_cpp_symbol_case_is_consistent_across_impact_coverage_and_diagrams(tmp_cfg):
    from sdd.diagrams import class_diagram
    from sdd.matching import matches_symbol
    sections(tmp_cfg, [{'id': 'api', 'facts': {'classes': ['device']}}])
    model = KnowledgeModel(classes={'hal::Device': ClassInfo('hal::Device', Location('api.h', 1))})
    report = compute(tmp_cfg, model, ['api.h'], 'a', 'b')
    assert not matches_symbol('hal::Device', ['device'])
    assert matches_symbol('hal::Device', ['Device'])
    assert report.sections == {}
    assert report.coverage['findings'][0]['reason'] == 'entity-outside-document-scope'
    assert class_diagram(model, ['device']) == ''


def test_manual_evidence_uses_literal_changed_paths(tmp_cfg):
    sections(tmp_cfg, [{'id': 'manual', 'kind': 'manual', 'output': 'notes.md'}])
    tmp_cfg.sdd_dir.mkdir()
    (tmp_cfg.sdd_dir / 'notes.md').write_text('---\nevidence_files: ["a.cpp"]\n---\n', encoding='utf-8')
    assert compute(tmp_cfg, KnowledgeModel(), ['*.cpp'], 'a', 'b').sections == {}
    assert 'manual' in compute(tmp_cfg, KnowledgeModel(), ['a.cpp'], 'a', 'b').sections


def test_old_impact_json_remains_readable(tmp_path):
    path = tmp_path / 'impact.json'
    path.write_text(json.dumps({'base': 'a', 'head': 'b'}), encoding='utf-8')
    assert ImpactReport.load(path).coverage == {}


def test_run_cannot_silently_skip_requested_coverage_gate(monkeypatch):
    monkeypatch.setattr('sdd.cli.cmd_extract', lambda args: pytest.fail('Invalid args must stop first'))
    with pytest.raises(SystemExit) as error:
        main(['run', '--fail-on-coverage-gap'])
    assert error.value.code == 2


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def revision_pair(cfg):
    root = cfg.source_root
    git(root, 'init')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.invalid')
    (root / 'old name.cpp').write_text('old', encoding='utf-8')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'base')
    base = git(root, 'rev-parse', 'HEAD')
    (root / 'old name.cpp').rename(root / '새 이름.cpp')
    git(root, 'add', '-A')
    git(root, 'commit', '-m', 'rename')
    return base, git(root, 'rev-parse', 'HEAD')


def test_diff_keeps_both_rename_paths_and_unicode(tmp_cfg):
    base, head = revision_pair(tmp_cfg)
    assert changed_files(tmp_cfg.source_root, base, head) == ['old name.cpp', '새 이름.cpp']


def test_cli_writes_review_and_optional_gate_before_generation(tmp_cfg, monkeypatch, capsys):
    base, head = revision_pair(tmp_cfg)
    model = KnowledgeModel(meta={'source_commit': head})
    model.save(tmp_cfg.facts_path)
    args = ['--config', str(tmp_cfg.root / 'sdd.yaml'), 'impact', '--base', base]
    assert main(args) == 0
    assert main(args + ['--fail-on-coverage-gap']) == 2
    report = ImpactReport.load(tmp_cfg.build_dir / 'impact.json')
    assert report.head == head and report.coverage['status'] == 'needs-review'
    assert 'old name.cpp' in (tmp_cfg.build_dir / 'impact-review.md').read_text(encoding='utf-8')
    monkeypatch.setattr('sdd.cli.cmd_extract', lambda args: 0)
    monkeypatch.setattr('sdd.cli.cmd_generate', lambda args: pytest.fail('Must stop before generation'))
    assert main(['--config', str(tmp_cfg.root / 'sdd.yaml'), 'run', '--base', base, '--fail-on-coverage-gap']) == 2
    assert '검토 항목' in capsys.readouterr().out


@pytest.mark.parametrize('stale_side', ['head', 'base'])
def test_cli_rejects_facts_from_wrong_revision(tmp_cfg, stale_side):
    base, head = revision_pair(tmp_cfg)
    KnowledgeModel(meta={'source_commit': base if stale_side == 'head' else head}).save(tmp_cfg.facts_path)
    previous = tmp_cfg.root / 'base.json'
    KnowledgeModel(meta={'source_commit': head}).save(previous)
    args = ['--config', str(tmp_cfg.root / 'sdd.yaml'), 'impact', '--base', base]
    if stale_side == 'base':
        args += ['--base-facts', str(previous)]
    assert main(args) == 1
    assert not (tmp_cfg.build_dir / 'impact.json').exists()


def test_익명_구조체는_범위_검토_항목이_아니다(tmp_cfg):
    """설정의 어떤 패턴으로도 고를 수 없으므로 보고해도 해결할 방법이 없다."""
    anon = 'Ctx::(unnamed struct at /home/someone/build/src/ctx.h:33:2)'
    sections(tmp_cfg, [{'id': 'ipa', 'watch': ['src/**'], 'facts': {'classes': ['Ctx']}}])
    model = KnowledgeModel(classes={
        'Ctx': ClassInfo('Ctx', Location('src/ctx.h', 10)),
        anon: ClassInfo(anon, Location('src/ctx.h', 33)),
    })
    report = compute(tmp_cfg, model, ['src/ctx.h'], 'a', 'b')
    names = [f['name'] for f in report.coverage['findings']]
    assert anon not in names
    assert '/home/someone' not in review_markdown(report)
    # 익명 구조체를 담은 클래스는 그대로 범위에 잡힌다.
    assert any(item['name'] == 'Ctx' for item in report.coverage['entities'])


def test_고를_수_있는_클래스는_계속_보고한다(tmp_cfg):
    sections(tmp_cfg, [{'id': 'ipa', 'watch': ['src/**'], 'facts': {'classes': ['Manager']}}])
    model = KnowledgeModel(classes={'Ctx': ClassInfo('Ctx', Location('src/ctx.h', 10))})
    report = compute(tmp_cfg, model, ['src/ctx.h'], 'a', 'b')
    assert [f['name'] for f in report.coverage['findings']] == ['Ctx']


def test_impact_config_changes_option_adds_design_section_without_manuscript(tmp_cfg):
    import yaml
    base, head = revision_pair(tmp_cfg)
    KnowledgeModel(meta={'source_commit': head}).save(tmp_cfg.facts_path)
    section = dict(id='device', title='장치', design_requirements=[dict(id='stop', question='종료는 무엇입니까?')],
                   design_topics=[dict(id='stop', title='종료', question='종료를 설명하세요.', covers=['stop'], sources=[])])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    args = ['--config', str(tmp_cfg.root / 'sdd.yaml'), 'impact', '--base', base]
    assert main(args) == 0
    assert 'device' not in ImpactReport.load(tmp_cfg.build_dir / 'impact.json').sections
    assert main(args + ['--config-changes']) == 0
    assert ImpactReport.load(tmp_cfg.build_dir / 'impact.json').sections['device'] == ['원고가 아직 없음']
