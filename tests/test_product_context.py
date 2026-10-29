"""Fictional product configurations only; never real support/performance claims."""
import copy
import hashlib

import pytest
import yaml

from sdd import evidence
from sdd.design_reuse import topic_inputs
from sdd.facts.model import KnowledgeModel
from sdd.product_context import bind, validate_text
from sdd.site_markdown import _render


@pytest.fixture
def products(tmp_cfg):
    cfg = tmp_cfg
    cfg.raw['products'] = {'file': 'products.yaml'}
    text = 'FICTIONAL TEST ONLY. Feature capture is offered on sensor A with build option X.\n'
    (cfg.root / 'spec.txt').write_bytes(text.encode('utf-8'))
    doc = {'id': 'spec-a', 'type': 'specification', 'supplier': 'Fictional fixture owner',
           'version': '1', 'date': '2026-01-01', 'valid_until': '2026-12-31',
           'product': 'fixture-a', 'release': 'r1', 'configuration': 'sensor-a-build-x',
           'feature': 'capture', 'conditions': ['sensor A', 'build X'], 'availability': 'offered',
           'file': 'spec.txt', 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    feature = {'id': 'capture', 'need': 'Acquire an image', 'usage': 'Fictional integration test',
               'availability': 'offered', 'conditions': ['sensor A', 'build X'], 'exclusions': ['sensor B'],
               'implementation': ['code'], 'evidence': ['spec-a'],
               'claims': [{'kind': 'structural', 'evidence': []}, {'kind': 'support', 'evidence': ['spec-a']}]}
    product = {'id': 'fixture-a', 'scope': 'product', 'release': 'r1', 'configuration': 'sensor-a-build-x',
               'simulation': True, 'as_of': '2026-10-30', 'features': [feature]}
    second = copy.deepcopy(product)
    second.update(id='fixture-b', configuration='sensor-b-build-y')
    second['features'][0].update(availability='unknown', conditions=['sensor B', 'build Y'],
                                 exclusions=[], evidence=[], claims=[{'kind': 'structural', 'evidence': []}])
    data = {'schema': 1, 'products': [product, second], 'evidence': [doc]}
    sections = []
    for name in ('a', 'b'):
        sections.append({'id': name, 'design_topics': [{'id': 'capture', 'question': 'What is offered?',
            'covers': ['capture'], 'product': {'id': 'fixture-' + name, 'feature': 'capture'},
            'sources': [{'id': 'code', 'file': 'capture.cpp', 'start': 'BEGIN', 'end': 'END'}]}],
            'design_requirements': [{'id': 'capture', 'question': 'What is offered?'}]})

    def save():
        (cfg.root / 'products.yaml').write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    save()
    return cfg, data, sections, save


def context(bound, index=0):
    return bound[index]['design_topics'][0]['_product_context']


def test_two_fictional_configurations_same_source_different_offering(products):
    cfg, _, sections, _ = products
    result = bind(cfg, sections)
    assert context(result)['availability'] == 'offered'
    assert context(result, 1)['availability'] == 'unknown'
    assert context(result, 1)['implementation'] == 'source-bound'
    assert context(result)['product']['simulation'] is True
    assert context(result)['feature']['conditions'] != context(result, 1)['feature']['conditions']
    assert context(result)['measurement'] == 'unknown'
    assert context(result)['human_review'] == 'pending'
    assert sections[0]['design_topics'][0]['sources'][0]['id'] == 'code'


@pytest.mark.parametrize('mutation,match', [
    (lambda d: d['evidence'][0].update(product='fixture-b'), 'wrong product'),
    (lambda d: d['evidence'][0].update(release='old'), 'wrong product'),
    (lambda d: d['evidence'][0].update(configuration='wrong'), 'wrong product'),
    (lambda d: d['evidence'][0].update(valid_until='2026-01-02'), 'stale'),
    (lambda d: d['evidence'][0].update(sha256='0' * 64), 'bytes changed'),
    (lambda d: d['evidence'][0].update(conditions=['different sensor']), 'conditions differ'),
    (lambda d: d['evidence'][0].update(availability='unsupported'), 'Conflicting'),
    (lambda d: d['evidence'][0].update(file='../outside.txt'), 'local relative'),
])
def test_wrong_stale_tampered_or_conflicting_evidence_fails(products, mutation, match):
    cfg, data, sections, save = products
    mutation(data)
    save()
    with pytest.raises(ValueError, match=match):
        bind(cfg, sections)


def test_actual_material_tampering_fails_even_without_source_commit_change(products):
    cfg, _, sections, _ = products
    before = (cfg.root / 'products.yaml').read_bytes()
    (cfg.root / 'spec.txt').write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='bytes changed'):
        bind(cfg, sections)
    assert (cfg.root / 'products.yaml').read_bytes() == before


def test_measurement_cannot_supply_offering_assurance_from_an_unknown_spec(products):
    cfg, data, sections, save = products
    data['evidence'][0]['availability'] = 'unknown'
    measured = copy.deepcopy(data['evidence'][0])
    measured.update(id='measured', type='measurement', availability='offered')
    data['evidence'].append(measured)
    feature = data['products'][0]['features'][0]
    feature['evidence'].append('measured')
    save()
    ctx = context(bind(cfg, sections))
    assert ctx['availability'] == 'unknown'
    assert 'support' in ctx['unresolved_claims']


def test_measurement_is_conditional_unsupported_is_explicit_and_missing_claims_stay_unknown(products):
    cfg, data, sections, save = products
    doc = data['evidence'][0]
    doc.update(type='measurement', availability='unknown')
    feature = data['products'][0]['features'][0]
    feature['availability'] = 'unknown'
    feature['claims'] = [{'kind': kind, 'evidence': ['spec-a']} for kind in ('performance', 'comparison', 'support')]
    save()
    ctx = context(bind(cfg, sections))
    assert ctx['availability'] == 'unknown' and ctx['measurement'] == 'conditional'
    assert ctx['allowed_claims'] == ['performance']
    assert ctx['unresolved_claims'] == ['comparison', 'support']
    feature['availability'] = doc['availability'] = 'unsupported'
    doc['type'] = 'specification'
    save()
    assert context(bind(cfg, sections))['availability'] == 'unsupported'


def test_product_only_changes_only_affected_topic_identity_and_no_effect_for_legacy(products):
    cfg, data, sections, save = products
    model = KnowledgeModel(meta={'source_commit': 'a' * 40})
    old = bind(cfg, sections)
    pins = [topic_inputs(model, sec, 'fixed') for sec in old]
    data['products'][0]['features'][0]['usage'] = 'Changed customer integration use'
    save()
    new = bind(cfg, sections)
    assert topic_inputs(model, new[0], 'fixed') != pins[0]
    assert topic_inputs(model, new[1], 'fixed') == pins[1]
    assert bind(cfg, [{'id': 'legacy'}]) == [{'id': 'legacy'}]
    assert bind(cfg, sections) == new


def test_unsupported_performance_comparison_and_offering_guarantees_rejected(products):
    cfg, _, sections, _ = products
    topic = bind(cfg, sections)[1]['design_topics'][0]
    for text in ('30fps로 처리합니다.', '경쟁 제품보다 우수합니다.', '이 제품에서 제공합니다.'):
        with pytest.raises(ValueError):
            validate_text(topic, [{'text': text}])
    validate_text(topic, [{'text': '코드에 구현되어 있지만 제품 제공 여부는 확인되지 않았습니다.'}])


def test_material_record_keeps_origin_and_does_not_link_to_source_git_host(products):
    cfg, _, sections, _ = products
    source = bind(cfg, sections)[0]['design_topics'][0]['sources'][1]
    from sdd.product_context import record
    rec = record(source, 'a' * 40)
    model = KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence={'a/capture/product-spec-a': rec})
    body = f"Test. `{rec['file']}:1`\n\n근거 원문: [{rec['file']}:1](#source-1111111111111111)"
    rendered, _, _ = _render(body, 'a.md', set(), model, 'https://host/repo', 'a' * 40)
    assert '/blob/' not in rendered and 'href="#source-1111111111111111"' in rendered
    assert rec['origin'] == 'product-material'


def test_reserved_material_cannot_be_injected_without_loader(products):
    cfg, _, sections, _ = products
    bound = bind(cfg, sections)
    with pytest.raises(ValueError, match='generator-owned'):
        bind(cfg, bound)


def test_existing_trial_clone_and_snapshot_keep_local_product_inputs(products, tmp_path):
    from sdd.trial_workspace import clone_config, write_snapshot, validate_output
    from sdd.config import load
    cfg, _, sections, _ = products
    cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    expected = cfg.sections()
    trial_dir = tmp_path/'trial'
    validate_output(cfg, trial_dir)
    trial = clone_config(cfg, trial_dir)
    trial_dir.mkdir()
    assert trial.sections() == expected
    saved = write_snapshot(trial, trial_dir/'sdd.yaml')
    assert load(saved).sections() == expected
    with pytest.raises(ValueError, match='isolated'):
        validate_output(cfg, cfg.root/'spec.txt')
