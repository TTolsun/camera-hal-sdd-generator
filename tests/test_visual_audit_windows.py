"""A reviewed window includes its source ownership, not unrelated page chrome."""
import json
import pytest

from sdd.visual_audit import (Document, WINDOW_BINDING, inventory_page, policy, source_window)
from test_visual_audit import document


@pytest.mark.parametrize('context',['','Context '])
@pytest.mark.parametrize('comment',['','<!-- separator -->'])
def test_plain_anchor_opens_the_actual_neighboring_source_panel(tmp_path,context,comment):
    text=document('<p>'+context+'<a id="source-0123456789abcdef"></a></p>'+comment+'<details><summary>Guide</summary>'
                  '<pre>Three real reading steps.</pre></details>')
    window=source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')
    assert 'Three real reading steps.' in window
    assert 'structure_sha256' in window
    changed=source_window(Document(text.replace('Three real','Four real')),'source-0123456789abcdef',root=tmp_path,page='guide.html')
    assert changed!=window


def test_cross_page_file_pin_stays_conservative_but_review_scope_excludes_chrome(tmp_path):
    path=tmp_path/'source.html'
    source=('<html><nav>old menu</nav><main><h1>Actual API</h1><article>'
            '<h2 id="owner">Owner</h2><h3 id="source-window">Conditions</h3><p>Exact condition.</p>'
            '</article><footer>old status</footer></main></html>')
    reader=document('<h2 id="one">Question</h2><p>Read the condition. '
                    '<a class="citation" href="source.html#source-window">source</a></p>')
    path.write_text(source,encoding='utf-8')
    def inspect():return inventory_page(reader,'guide.html',policy(),source_commit='a'*40,root=tmp_path)[1]
    old=inspect()
    path.write_text(source.replace('old menu','new menu').replace('old status','new status'),encoding='utf-8')
    assert inspect()['fingerprint']!=old['fingerprint']
    selected=source_window(Document(path.read_text(encoding='utf-8')),'source-window',root=tmp_path,page='source.html')
    assert 'new menu' not in selected and 'new status' not in selected
    path.write_text(source.replace('Exact condition.','Changed condition.'),encoding='utf-8')
    assert inspect()['fingerprint']!=old['fingerprint']


def test_heading_source_ownership_and_title_are_bound_and_visible(tmp_path):
    original='<html><h1>Camera API</h1><article><h2>Configure</h2><h3 id="conditions">Conditions</h3><p>same text</p></article><footer>not source</footer></html>'
    def window(text):return source_window(Document(text),'conditions',root=tmp_path,page='api.html')
    before=window(original)
    binding=json.loads(before.rsplit(WINDOW_BINDING,1)[1])
    assert [h['text'] for h in binding['heading_context']]==['Camera API','Configure']
    assert 'not source' not in before
    assert window(original.replace('<h2>Configure</h2>','<h2>Stop</h2>'))!=before
    assert window(original.replace('Camera API','Other API'))!=before


@pytest.mark.parametrize('comment',['','<!-- separator -->'])
def test_bare_anchor_resolves_its_details_sibling_like_reader_tools(tmp_path,comment):
    text=document('<a id="source-0123456789abcdef"></a>'+comment+'<details><summary>Source</summary><pre>Original</pre></details>')
    before=source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')
    assert 'Original' in before
    assert source_window(Document(text.replace('Original','Changed')),'source-0123456789abcdef',root=tmp_path,page='guide.html')!=before


def test_nested_chrome_cannot_truncate_or_enter_a_heading_source_window(tmp_path):
    text=document('<h2 id="source">Source</h2><nav><h2>Menu</h2></nav><p>Actual evidence.</p>'
                  '<aside>Aside content.</aside><footer>Footer content.</footer>')
    before=source_window(Document(text),'source',root=tmp_path,page='guide.html')
    assert 'Actual evidence.' in before
    assert all(part not in before for part in ('Menu','Aside content.','Footer content.'))
    assert source_window(Document(text.replace('Actual evidence.','Changed evidence.')),'source',root=tmp_path,page='guide.html')!=before


def test_ordinary_fragment_binds_its_target_instead_of_neighboring_details(tmp_path):
    text=document('<p id="condition">Original condition.</p><details><summary>Supplement</summary>Other text.</details>')
    before=source_window(Document(text),'condition',root=tmp_path,page='guide.html')
    assert 'Original condition.' in before and 'Other text.' not in before
    assert source_window(Document(text.replace('Original condition.','Changed condition.')),'condition',root=tmp_path,page='guide.html')!=before


@pytest.mark.parametrize('tag',['nav','aside','footer'])
@pytest.mark.parametrize('target',['h2','p','a'])
def test_excluded_targets_cannot_be_empty_resolved_evidence(tmp_path,tag,target):
    text=document('<'+tag+'><'+target+' id="source">Hidden target</'+target+'></'+tag+'>')
    with pytest.raises(ValueError,match='inside excluded navigation'):
        source_window(Document(text),'source',root=tmp_path,page='guide.html')


def test_moving_source_panel_changes_readable_heading_ownership(tmp_path):
    panel='<p><a id="source-0123456789abcdef"></a></p><details><summary>Source</summary><pre>Same code.</pre><nav>Menu</nav></details>'
    before=document('<h2 id="first">First API</h2>'+panel+'<h2 id="second">Second API</h2>')
    after=document('<h2 id="first">First API</h2><h2 id="second">Second API</h2>'+panel)
    def window(text):return source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')
    assert window(before)!=window(after)
    assert 'First API' in window(before) and 'Second API' in window(after)
    assert 'Menu' not in window(before)


def test_external_page_heading_cannot_expand_across_unowned_articles_and_dialogs(tmp_path):
    text='<html><h1 id="title">Title</h1><article><p>Evidence.</p></article><dialog>Other content.</dialog></html>'
    with pytest.raises(ValueError,match='no owning article'):
        source_window(Document(text),'title',root=tmp_path,page='guide.html')
    source='<h2 id="source-0123456789abcdef">Source</h2><details><summary>Excerpt</summary>Code.</details>'
    with pytest.raises(ValueError,match='no owning article'):
        source_window(Document(source),'source-0123456789abcdef',root=tmp_path,page='guide.html')


def test_heading_ownership_text_excludes_nested_navigation(tmp_path):
    text=document('<h2>API<nav>Old menu</nav></h2><p id="condition">Value.</p>')
    before=source_window(Document(text),'condition',root=tmp_path,page='guide.html')
    assert 'Old menu' not in before
    assert source_window(Document(text.replace('Old menu','New menu')),'condition',root=tmp_path,page='guide.html')==before


def test_source_format_heading_opens_panel_before_section_boundary_traversal(tmp_path):
    text=document('<h2 id="source-0123456789abcdef">Source</h2><details><summary>Excerpt</summary>'
                  '<h2>Declaration</h2><p>Actual code.</p></details>')
    before=source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')
    assert 'Actual code.' in before
    assert source_window(Document(text.replace('Actual code.','Changed code.')),'source-0123456789abcdef',root=tmp_path,page='guide.html')!=before
    assert source_window(Document(text.replace('>Source</h2>','>Changed source</h2>')),'source-0123456789abcdef',root=tmp_path,page='guide.html')!=before


def test_non_heading_window_cannot_climb_outside_owning_article(tmp_path):
    text='<details><summary>Outer</summary><article><p id="condition">Evidence.</p></article><p>Unrelated.</p></details>'
    selected=source_window(Document(text),'condition',root=tmp_path,page='guide.html')
    assert 'Evidence.' in selected
    assert 'Unrelated.' not in selected and 'Outer' not in selected


def test_source_id_on_article_cannot_select_its_external_sibling_panel(tmp_path):
    text='<article id="source-0123456789abcdef"><p>Evidence.</p></article><details><summary>Unrelated</summary>Other content.</details>'
    with pytest.raises(ValueError,match='crosses its owning article boundary'):
        source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')


@pytest.mark.parametrize('target',['p','a'])
def test_unowned_non_heading_targets_fail_before_panel_resolution(tmp_path,target):
    text='<'+target+' id="source-0123456789abcdef">Label</'+target+'><details><summary>Excerpt</summary>Code.</details>'
    with pytest.raises(ValueError,match='no owning article'):
        source_window(Document(text),'source-0123456789abcdef',root=tmp_path,page='guide.html')


@pytest.mark.parametrize('suffix,fragment',[('.html','source'),('.cpp','L1')])
def test_cross_file_byte_pin_detects_line_ending_changes(tmp_path,suffix,fragment):
    path=tmp_path/('source'+suffix)
    raw='<article><h2 id="source">Source</h2><p>Condition.</p></article>\n' if suffix=='.html' else 'void stop() {}\n'
    reader=document('<h2 id="one">Question</h2><p><a class="citation" href="'+path.name+'#'+fragment+'">source</a></p>')
    path.write_bytes(raw.encode())
    def inspect():return inventory_page(reader,'guide.html',policy(),source_commit='a'*40,root=tmp_path)[1]['fingerprint']
    before=inspect();path.write_bytes(raw.replace('\n','\r\n').encode())
    assert inspect()!=before
