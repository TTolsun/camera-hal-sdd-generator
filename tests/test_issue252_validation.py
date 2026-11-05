from pathlib import Path
import importlib.util
import pytest
import json
import shutil
import yaml
from types import SimpleNamespace

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


@pytest.mark.parametrize('eol',['\n','\r\n'])
def test_visual_metadata_revalidation_preserves_body_and_historical_aliases(eol):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/revalidate_visuals.py'
    spec=importlib.util.spec_from_file_location('issue252_visual_metadata',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    header='---\nagent: cli/claude/historical\ngenerated_visuals: &original\n  schema: 1\n  records: {old: {model: historical}}\nhistorical_graph_metadata: *original\n---\n'
    body='# Unchanged\n\n```cpp\nint old_value = 0;\n```\n'.replace('\n',eol).encode()
    original=header.replace('\n',eol).encode()+body
    artifact={'schema':1,'records':{'old':{'model':'historical','revalidated':True}}}
    updated=module.replace_visual_metadata(original,artifact)
    assert updated.endswith(body)
    old_meta,_=module.split_frontmatter(original.decode().replace('\r\n','\n'))
    new_meta,_=module.split_frontmatter(updated.decode().replace('\r\n','\n'))
    assert new_meta['generated_visuals']==artifact
    assert new_meta['historical_graph_metadata']==old_meta['generated_visuals']
    assert new_meta['agent']==old_meta['agent']
    row=dict(page='example.md',original_sha256=module.hashlib.sha256(original).hexdigest(),
             updated_sha256=module.hashlib.sha256(updated).hexdigest(),body_unchanged=True,new_inference=False)
    assert module.retain_revalidation_row(row,original,updated)==row
    if eol=='\r\n':
        with pytest.raises(ValueError,match='byte identities'):
            module.retain_revalidation_row(row,original.replace(b'\r\n',b'\n'),updated)
    with pytest.raises(ValueError,match='byte identities'):
        module.retain_revalidation_row(row,original,updated+b'changed')


def test_crlf_revalidation_workflow_retains_actual_file_hashes_on_repeat(tmp_path,monkeypatch):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/revalidate_visuals.py'
    spec=importlib.util.spec_from_file_location('issue252_visual_repeat',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    run=tmp_path/'run';manuscripts=run/'manuscripts';manuscripts.mkdir(parents=True)
    original=b'---\r\nagent: synthetic-historical-model\r\ngenerated_visuals:\r\n  schema: 1\r\n  records: {}\r\n---\r\n# Unchanged body\r\n\r\nEvidence text.\r\n'
    target=manuscripts/'legacy.md';target.write_bytes(original)
    cfg=SimpleNamespace(sdd_dir=manuscripts,facts_path=run/'facts.json',sections=lambda:[{'id':'legacy'}])
    monkeypatch.setattr(module,'RUN',run)
    monkeypatch.setattr(module,'load',lambda _:cfg)
    monkeypatch.setattr(module.KnowledgeModel,'load',lambda _:object())
    monkeypatch.setattr(module,'for_page',lambda cfg,_:cfg)
    monkeypatch.setattr(module,'section_output',lambda _:'legacy.md')
    monkeypatch.setattr(module.generated_visuals,'plans',lambda *_:True)
    def resolve(_cfg,_model,_section,artifact):
        if not artifact.get('current'):
            raise ValueError('Synthetic historical binding needs metadata revalidation.')
    monkeypatch.setattr(module.generated_visuals,'resolve',resolve)
    monkeypatch.setattr(module.generated_visuals,'generate',lambda *_:dict(schema=1,current=True,records={'synthetic':{'reused':True,'citation_binding_revalidation':{'new_inference':False}}}))
    module.main()
    report=run/'visual-revalidation.json';first=report.read_bytes();row=json.loads(first)[0]
    snapshot=run/row['original_file']
    assert snapshot.read_bytes()==original
    assert row['original_sha256']==module.hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert row['updated_sha256']==module.hashlib.sha256(target.read_bytes()).hexdigest()
    current=target.read_bytes()
    module.main()
    assert report.read_bytes()==first and target.read_bytes()==current
    replacement=original.replace(b'Evidence text.',b'New public evidence text.')
    target.write_bytes(replacement)
    module.main()
    next_report=report.read_bytes();new_row=json.loads(next_report)[0]
    assert new_row['original_file']!=row['original_file']
    assert snapshot.read_bytes()==original
    assert (run/new_row['original_file']).read_bytes()==replacement
    assert new_row['updated_sha256']==module.hashlib.sha256(target.read_bytes()).hexdigest()
    assert any(p.read_bytes()==first for p in (run/'visual-revalidation-history').glob('*.json'))
    module.main()
    assert report.read_bytes()==next_report
