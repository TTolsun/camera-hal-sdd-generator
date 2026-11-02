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
