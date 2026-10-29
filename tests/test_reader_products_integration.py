"""Exercise new inputs through existing generation/publication transactions."""
import copy
import hashlib
import json

import pytest
import yaml

from test_generated_design import generated
from test_product_context import products
from sdd import generated_design
from sdd.generate import Generator
from sdd.export_site import export_site
from sdd.impact import ImpactReport, config_changes
from sdd.product_context import record


def test_scope_artifact_change_and_repeated_generation_preserve_boundaries(generated, tmp_cfg):
    section, model, save, agent = generated
    section['reader_profile'] = 'team'
    # This fixture answers the full fixed team profile with one representative
    # source-bound requirement; it does not claim a real reader task test.
    section['design_requirements'][0]['aspects'] = ['role', 'inputs', 'outputs', 'boundaries']
    section['reader_scope'] = {'revision': 1, 'change_reason': 'Fixed fixture scope.',
        'tasks': [{'id': 'collaborate', 'goal': 'Find the stop responsibility.',
                   'completion': 'Find the answer and evidence.', 'requirements': ['shutdown']}],
        'optional': [], 'excluded': [{'id': 'all-functions', 'reason': 'Not a reference manual.'}],
        'removed_requirements': []}
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    site = export_site(tmp_cfg)
    before = path.read_bytes()
    manifest = (site/'site-manifest.json').read_bytes()
    report = json.loads((site/'reader-scope.json').read_text(encoding='utf-8'))
    assert report['pages']['device.md']['structural'] == 'linked'
    assert report['pages']['device.md']['human_task_test'] == 'pending'
    calls = len(agent.calls)
    impact = ImpactReport('a'*40, 'a'*40, sections={'device': ['same fixed input']})
    Generator(tmp_cfg, model, agent).run(impact=impact)
    assert len(agent.calls) == calls
    assert path.read_bytes() == before
    assert export_site(tmp_cfg) == site
    assert (site/'site-manifest.json').read_bytes() == manifest
    section['reader_scope']['tasks'][0]['completion'] += ' Include the exception.'
    save()
    with pytest.raises(ValueError, match='재생성'):
        export_site(tmp_cfg)
    with pytest.raises(ValueError, match='newer revision'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == before and (site/'site-manifest.json').read_bytes() == manifest


def test_product_only_change_blocks_old_manuscript_then_failed_generation_preserves_it(products, generated, tmp_cfg):
    _, data, _, save_product = products
    section, model, save, agent = generated
    feature = data['products'][0]['features'][0]
    feature['implementation'] = ['stop']
    save_product()
    section['design_topics'][0]['product'] = {'id': 'fixture-a', 'feature': 'capture'}
    save()
    bound = tmp_cfg.sections()[0]
    for source in bound['design_topics'][0]['sources']:
        if source.get('kind') == 'product':
            model.evidence[f"device/stop/{source['id']}"] = record(source, model.meta['source_commit'])
    model.save(tmp_cfg.facts_path)
    path = Generator(tmp_cfg, model, agent).run()[0]
    site = export_site(tmp_cfg)
    before = path.read_bytes()
    manifest = (site/'site-manifest.json').read_bytes()
    from sdd.localization_cli import prepare_catalog
    catalog = tmp_cfg.root/'translation-review.json'
    prepare_catalog(tmp_cfg, catalog, translate=False)
    prior_pages = json.loads(catalog.read_text(encoding='utf-8'))['pages']
    data['products'][0]['features'][0]['usage'] = 'New fictional customer condition.'
    save_product()
    assert 'device' in config_changes(tmp_cfg, model)
    with pytest.raises(ValueError, match='재생성'):
        export_site(tmp_cfg)
    class Failed:
        def chat(self, *args, **kwargs):
            return '{"statements": []}'
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, Failed()).run()
    assert path.read_bytes() == before
    assert (site/'site-manifest.json').read_bytes() == manifest
    # A source-identical product-material revision requires a new manuscript
    # and page translation review. No fake translation is published by this test.
    material = tmp_cfg.root/'spec.txt'
    material.write_bytes(material.read_bytes() + b'FICTIONAL revision 2: clarified integration scope.\n')
    data['evidence'][0].update(version='2', sha256=hashlib.sha256(material.read_bytes()).hexdigest())
    save_product()
    for source in tmp_cfg.sections()[0]['design_topics'][0]['sources']:
        if source.get('kind') == 'product':
            model.evidence[f"device/stop/{source['id']}"] = record(source, model.meta['source_commit'])
    model.save(tmp_cfg.facts_path)
    calls = len(agent.calls)
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) > calls
    prepare_catalog(tmp_cfg, catalog, translate=False)
    current = json.loads(catalog.read_text(encoding='utf-8'))
    assert current['pages']['device.html'] != prior_pages['device.html']
    assert current['review_status'] == 'human-review-pending'
