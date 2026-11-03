"""Partial UI previews preserve the other pages' searchable public entries."""
import importlib.util
import json
from pathlib import Path


def test_selected_pages_replace_search_entries_in_both_languages(tmp_path):
    tool=Path(__file__).resolve().parents[1]/'examples/libcamera/validation/issue215/preview_search.py'
    spec=importlib.util.spec_from_file_location('issue215_preview_search',tool)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    public,stage=tmp_path/'public',tmp_path/'stage'
    for prefix in ('','en/'):
        original=[dict(title='Old selected',url='guide.html#old'),
                  dict(title='Deferred document',url='deferred.html#question')]
        updated=[dict(title='New selected',url='guide.html#new')]
        for root,entries in ((public,original),(stage,updated)):
            path=root/(prefix+'assets/search.json');path.parent.mkdir(parents=True)
            path.write_text(json.dumps(entries),encoding='utf-8')
    module.merge_search(public,stage,{'guide.md'})
    for prefix in ('','en/'):
        entries=json.loads((stage/(prefix+'assets/search.json')).read_bytes())
        assert [r['url'] for r in entries]==['deferred.html#question','guide.html#new']
        assert json.loads((public/(prefix+'assets/search.json')).read_bytes())[0]['title']=='Old selected'
