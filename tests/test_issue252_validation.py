from pathlib import Path
import importlib.util
import pytest
import json
import shutil
import yaml

@pytest.mark.parametrize('delimiter',['`','~'])
def test_visual_audit_ignores_shorter_fences_inside_a_longer_code_block(delimiter):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/audit.py'
    spec=importlib.util.spec_from_file_location('issue252_audit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='## Before\n'+delimiter*4+'text\n'+delimiter*3+'\n## Inside code\n'+delimiter*4+'not-a-close\n### Also code\n'+delimiter*4+'\n### After\n'
    assert module.document_items(text)==[dict(anchor='item-01',title='Before',level=2),dict(anchor='item-02',title='After',level=3)]


def test_refinement_preserves_concurrently_integrated_lifetime_figures(tmp_path):
    root=Path(__file__).parents[1]
    path=root/'examples/libcamera/validation/issue252/refine.py'
    spec=importlib.util.spec_from_file_location('issue252_refine',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=tmp_path
    module.RUN=tmp_path/'build/issue252/run'
    config=module.RUN/'config';config.mkdir(parents=True)
    example=tmp_path/'examples/libcamera/config';example.mkdir(parents=True)
    for name in ['sections.yaml','visuals.yaml']:
        source=root/'examples/libcamera/config'/name
        shutil.copy2(source,config/name);shutil.copy2(source,example/name)
    audit=module.RUN/'audits/accuracy-01';audit.mkdir(parents=True)
    (audit/'review.json').write_text(json.dumps({'status':'needs-work'}))
    (module.RUN/'public-base-integration.json').write_text('{}')
    baseline=module.RUN.parent/'public/publication/issue214/config';baseline.mkdir(parents=True)
    shutil.copy2(config/'visuals.yaml',baseline/'visuals.yaml')
    def resources(p):
        return [v for v in yaml.safe_load(p.read_bytes())['sections']['request-lifecycle']
                if v.get('topic')=='resources']
    expected=resources(example/'visuals.yaml')
    assert {'completed-but-not-returned','completion-notification-order','completion-change-checks'} <= {v['id'] for v in expected}
    for _ in range(2):
        module.main()
        assert resources(example/'visuals.yaml')==expected
        assert resources(config/'visuals.yaml')==expected
