import copy
import hashlib
import json
from dataclasses import replace

import pytest
import yaml

from sdd.publication_plan import check_baseline, check_catalog, check_reports
from sdd.validation_stage import stage


def test_baseline_summary_terms_and_output_are_not_silently_lost(tmp_cfg):
    section = dict(id='guide', title='Guide', output='guide.md', design_requirements=[dict(id='required')],
        design_topics=[dict(id='topic', parts=[dict(id='summary', role='summary', question='Conclusion')],
                            answer_contract=dict(required_terms=[['necessary']]))])
    baseline = tmp_cfg.root/'baseline.yaml'
    reference = tmp_cfg.root/'reference.yaml'
    reference.write_text(yaml.safe_dump(dict(sections=[section])), encoding='utf-8')
    baseline.write_text(yaml.safe_dump(dict(paths=dict(sections_file=str(reference)))), encoding='utf-8')
    tmp_cfg.raw['publication'] = dict(baseline_config=str(baseline))
    for mutation in ('summary', 'terms', 'output'):
        effective = copy.deepcopy(section)
        if mutation == 'summary':
            effective['design_topics'][0]['parts'] = []
        elif mutation == 'terms':
            effective['design_topics'][0]['answer_contract']['required_terms'] = []
        else:
            effective['output'] = 'other.md'
        tmp_cfg.sections_file.write_text(yaml.safe_dump(dict(sections=[effective])), encoding='utf-8')
        with stage(), pytest.raises(ValueError, match='lost baseline contracts'):
            check_baseline(tmp_cfg)
    tmp_cfg.sections_file.write_text(yaml.safe_dump(dict(sections=[section])), encoding='utf-8')
    tmp_cfg.agent.runner, tmp_cfg.agent.model = 'claude', 'inhouse-model'
    tmp_cfg.agent.args = ['--effort', 'high']
    with stage():
        assert check_baseline(tmp_cfg)['path'] == str(baseline)


def test_catalog_checks_placeholder_units_and_shared_section_label(tmp_cfg):
    path = tmp_cfg.root/'catalog.json'
    tmp_cfg.raw['site'] = dict(english_catalog=str(path))
    def write(strings):
        path.write_text(json.dumps(dict(strings=strings)), encoding='utf-8')
    write({'절 전체 근거 {{1}}개': 'Clause evidence {{1}}'})
    with pytest.raises(ValueError, match='shared-label regression'):
        check_catalog(tmp_cfg)
    write({'절 전체 근거 {{1}}개': 'Section evidence {{2}}'})
    with pytest.raises(ValueError, match='placeholders'):
        check_catalog(tmp_cfg)
    write({'절 전체 근거 {{1}}개': 'Section evidence {{1}}'})
    check_catalog(tmp_cfg)


def test_required_report_missing_hash_and_stage_binding_are_checked(tmp_cfg):
    path = tmp_cfg.root/'review.json'
    row = dict(path=str(path), gate='before-export', producer='independent-review',
               sha256='0'*64, bindings=dict(status='passed', input_sha256='current'))
    tmp_cfg.raw['publication'] = dict(reports=[row])
    check_reports(tmp_cfg, 'before-generation')
    with pytest.raises(FileNotFoundError):
        check_reports(tmp_cfg, 'before-export')
    path.write_text(json.dumps(dict(status='passed', input_sha256='previous')), encoding='utf-8')
    with pytest.raises(ValueError, match='hash'):
        check_reports(tmp_cfg, 'before-export')
    row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='stage/input/status'):
        check_reports(tmp_cfg, 'before-export')
    path.write_text(json.dumps(dict(status='passed', input_sha256='current')), encoding='utf-8')
    row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert check_reports(tmp_cfg, 'before-export')[0]['verified']
