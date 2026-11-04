import pytest
import copy
import hashlib
from types import SimpleNamespace
import yaml

from sdd.scenario_sections import _same_encoded_overview


def overview(graph):
    return '## Calls\n\nStatic relationships, not runtime order.\n\n```mermaid\n'+graph+'\n```'


def test_encoding_refresh_compares_literal_labels_without_reinterpreting_entities():
    old = 'flowchart LR\n a["A&lt;T&gt; &amp;quot; #10;"]\n a -->|"call()"| b'
    new = 'flowchart LR\n a["A#60;T#62; #38;quot; #35;10;"]\n a -->|"call#40;#41;"| b'
    assert _same_encoded_overview(overview(old), overview(new))


@pytest.mark.parametrize('change', ['label', 'edge', 'prose', 'extra-graph'])
def test_encoding_refresh_rejects_semantic_or_narrative_changes(change):
    old = overview('flowchart LR\n a["A"]\n a -->|"call()"| b')
    new = overview('flowchart LR\n a["A"]\n a -->|"call#40;#41;"| b')
    if change == 'label':new = new.replace('["A"]', '["B"]')
    if change == 'edge':new = new.replace('a -->', 'b -->')
    if change == 'prose':new = new.replace('not runtime order', 'runtime order')
    if change == 'extra-graph':new += '\n```mermaid\nflowchart LR\na-->b\n```'
    assert not _same_encoded_overview(old, new)


def test_refresh_revalidates_native_body_and_preserves_approval_and_origin(monkeypatch):
    from sdd import scenario_sections, generated_design
    from sdd.document_metadata import split_frontmatter
    old = overview('flowchart LR\n a["A&lt;T&gt;"]')
    new = overview('flowchart LR\n a["A#60;T#62;"]')
    details = '## Trace\n\nEvery original call remains.\n'
    body = 'Native authored explanation.\n\n'+old+'\n\n'+details
    expected = {'scenario_id':'s','entry':'A::run','scenario_fingerprint':'f'*64}
    digest = lambda value:hashlib.sha256(value.strip().encode()).hexdigest()
    metadata = {**expected,'agent':'historical-native-cli','human_review':'pending',
                'generated_design':{'body_sha256':digest(body),'answers':{'s':['original']}}}
    manuscript = '---\n'+yaml.safe_dump(metadata)+'---\n'+body
    original = copy.deepcopy(metadata);checked=[]
    def verify(model, section, text, cfg=None):
        meta, value = split_frontmatter(text)
        assert meta['generated_design']['body_sha256']==digest(value)
        checked.append(text)
    monkeypatch.setattr(generated_design,'verify',verify)
    monkeypatch.setattr(scenario_sections,'appendix',lambda *args:(SimpleNamespace(overview=new,details=details),expected))
    previous={'source_commit':'a'*40,'metadata':expected,'overview':old,'details':details}
    result=scenario_sections.refresh_encoded_appendix(None,SimpleNamespace(meta={'source_commit':'a'*40}),{},manuscript,previous)
    meta,value=split_frontmatter(result)
    assert value==body.replace(old,new)
    assert meta['agent']==original['agent'] and meta['human_review']=='pending'
    assert meta['generated_design']['answers']==original['generated_design']['answers']
    assert len(checked)==2 and checked==[manuscript,result]
    assert meta['managed_format_refresh'][0]['new_inference'] is False
    with pytest.raises(ValueError,match='another source commit'):
        scenario_sections.refresh_encoded_appendix(None,SimpleNamespace(meta={'source_commit':'b'*40}),{},manuscript,previous)
