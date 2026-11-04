from pathlib import Path
import importlib.util
import json
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'examples/libcamera/validation/issue211-virtual'
spec = importlib.util.spec_from_file_location('invocation_scope', DIRECTORY/'invocation_scope.py')
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def test_changed_invocation_projection_cannot_create_a_workspace(tmp_path):
    proof = json.loads((DIRECTORY/'invocation-options.json').read_bytes())
    proof['records'][0]['cam_arguments'].append('--file=frame-#.bin')
    fixture = tmp_path/'changed.json'
    fixture.write_text(json.dumps(proof))
    workspace = tmp_path/'workspace'
    with pytest.raises(ValueError, match='projection changed'):
        scope.attach(workspace, fixture)
    assert not workspace.exists()


def test_attachment_preserves_prior_feature_and_binds_all_new_materials(tmp_path):
    ids = ['official-cam-reader', 'execution-contract', 'reproduction-procedure']
    feature = {'id': 'wsl-virtual-capture', 'evidence': ids.copy(), 'conditions': ['recorded']}
    documents = [{'id': name, 'feature': feature['id'], 'file': name+'.json', 'sha256': 'a'*64} for name in ids]
    initial = {'schema': 1, 'products': [{'id': 'libcamera-official-cam-trial', 'features': [feature]}], 'evidence': documents}
    config = tmp_path/'config'
    config.mkdir()
    path = config/'products.yaml'
    path.write_text(yaml.safe_dump(initial))
    scope.attach(tmp_path, DIRECTORY/'invocation-options.json')
    result = yaml.safe_load(path.read_bytes())
    assert result['products'][0]['features'][0] == feature
    assert result['evidence'][:3] == documents
    selected = result['products'][0]['features'][1]
    evidence = {row['id']: row for row in result['evidence']}
    assert set(selected['evidence']) == {'invocation-'+name for name in ids} | {'invocation-options'}
    assert all(evidence[name]['feature'] == selected['id'] for name in selected['evidence'])
    assert (config/evidence['invocation-options']['file']).read_bytes() == scope.validate(DIRECTORY/'invocation-options.json')


def test_shipped_virtual_visuals_resolve_against_attached_topic_sources(tmp_cfg):
    """Fictional materials exercise the real recipe/attachment binding contract."""
    import hashlib
    from sdd.product_context import bind
    config = tmp_cfg.root/'config'
    config.mkdir(exist_ok=True)
    ids = ['official-cam-reader', 'execution-contract', 'reproduction-procedure']
    feature = dict(id='wsl-virtual-capture', need='Fixture need', usage='Synthetic binding test',
                   availability='unknown', conditions=['fixture only'], exclusions=[],
                   implementation=[], evidence=ids, claims=[])
    product = dict(id='libcamera-official-cam-trial', scope='project', release=scope.BASELINE,
                   configuration='fixture', simulation=True, as_of='2026-10-31', features=[feature])
    documents = []
    for ident in ids:
        body = b'Fictional binding fixture; no runtime result.\n'
        (config/(ident+'.txt')).write_bytes(body)
        documents.append(dict(id=ident, type='measurement', supplier='Synthetic fixture', version='1',
            date='2026-10-31', valid_until='2026-10-31', product=product['id'], release=scope.BASELINE,
            configuration='fixture', feature=feature['id'], conditions=feature['conditions'],
            availability='unknown', file=ident+'.txt', sha256=hashlib.sha256(body).hexdigest()))
    path = config/'products.yaml'
    path.write_text(yaml.safe_dump(dict(schema=1, products=[product], evidence=documents)))
    scope.attach(tmp_cfg.root, DIRECTORY/'invocation-options.json')
    tmp_cfg.raw['products'] = {'file': 'config/products.yaml'}
    tmp_cfg.paths['products_file'] = path
    section = yaml.safe_load((DIRECTORY/'section.yaml').read_bytes())
    section['design_topics'].insert(1, yaml.safe_load((DIRECTORY/'topic.yaml').read_bytes()))
    bound = bind(tmp_cfg, [section])[0]
    topics = {topic['id']: topic for topic in bound['design_topics']}
    plans = [yaml.safe_load((DIRECTORY/'visual.yaml').read_bytes())]
    plans += yaml.safe_load((DIRECTORY/'retained-visual-overrides.yaml').read_bytes())
    expected = {'virtual-frame-path', 'request-completion-order', 'submission-gate',
                'initial-submission', 'completion-flow', 'reproduction-flow'}
    assert len(plans) == len(expected)
    assert {plan['id'] for plan in plans} == expected
    for plan in plans:
        available = {source['id'] for source in topics[plan['topic']]['sources']}
        assert set(plan['sources']) <= available, (plan['id'], sorted(set(plan['sources']) - available))
