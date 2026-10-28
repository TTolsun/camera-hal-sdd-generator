import hashlib
import json

import pytest

from sdd.consistency_analysis import evidence, paragraph_refs
from sdd.facts.model import KnowledgeModel, Location, Message, Scenario
from sdd.scenario_document import build, fingerprint


def scenario_case(tmp_cfg):
    settings = {'id': 'flow', 'from': 'Entry::start()'}
    tmp_cfg.scenarios_file.write_text('scenarios:\n- id: flow\n  from: Entry::start()\n', encoding='utf-8')
    scenario = Scenario(id='flow', title='흐름', entry='Entry::start()', participants=['Entry', 'Worker'],
        messages=[Message('Entry', 'Worker', 'work', Location('worker.cpp', 3), '예약된 호출')], deferred=1)
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, scenarios={'flow': scenario})
    meta = dict(generation_method='extracted-scenario', scenario_id='flow', entry=scenario.entry,
                scenario_fingerprint=fingerprint(scenario, settings))
    note = next(p for p in build(scenario, settings).details.split('\n\n') if '예약 표시는' in p)
    return model, meta, note


def test_analysis_evidence_is_bound_to_real_schema_extractor_and_extracted_scenario(tmp_cfg):
    model, meta, note = scenario_case(tmp_cfg)
    refs = paragraph_refs(tmp_cfg, model, meta, note)
    assert refs == ['@analysis/scenario/flow']
    row = evidence(model, refs[0])
    assert row['kind'] == 'analysis-definition'
    assert row['sha256'] == hashlib.sha256(row['text'].encode()).hexdigest()
    data = json.loads(row['text'])
    assert data['project_source_commit'] == model.meta['source_commit']
    assert data['scenario']['messages_total'] == data['scenario']['deferred'] == 1
    assert {d['name'] for d in data['generator_definitions']} == {'Message', 'Scenario', '_deferred_targets', 'trace', 'build'}
    assert all(hashlib.sha256(d['text'].encode()).hexdigest() == d['sha256'] for d in data['generator_definitions'])


def test_analysis_proof_cannot_be_attached_to_arbitrary_product_claims_or_stale_scenario(tmp_cfg):
    model, meta, note = scenario_case(tmp_cfg)
    assert paragraph_refs(tmp_cfg, model, meta, 'Every callback always executes asynchronously.') == []
    assert paragraph_refs(tmp_cfg, model, {}, note) == []
    meta['scenario_fingerprint'] = 'tampered'
    with pytest.raises(ValueError, match='fingerprint'):
        paragraph_refs(tmp_cfg, model, meta, note)
    with pytest.raises(ValueError, match='Unknown scenario'):
        evidence(model, '@analysis/scenario/../../private')
