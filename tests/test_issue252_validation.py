from pathlib import Path
import importlib.util
import pytest

@pytest.mark.parametrize('delimiter',['`','~'])
def test_visual_audit_ignores_shorter_fences_inside_a_longer_code_block(delimiter):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/audit.py'
    spec=importlib.util.spec_from_file_location('issue252_audit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='## Before\n'+delimiter*4+'text\n'+delimiter*3+'\n## Inside code\n'+delimiter*4+'not-a-close\n### Also code\n'+delimiter*4+'\n### After\n'
    assert module.document_items(text)==[dict(anchor='item-01',title='Before',level=2),dict(anchor='item-02',title='After',level=3)]
