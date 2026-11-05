"""Static presentation changes invalidate item reviews without changing prose."""
import pytest
from sdd.visual_audit import apply_reviews, enforce, inventory_page, policy
from test_visual_audit import FIGURE, ledger


def report(body):
    options=policy()
    return dict(items=inventory_page('<html lang="ko"><body><article>'+body+
        '</article></body></html>','guide.html',options,source_commit='a'*40),policy=options,errors=[])


@pytest.mark.parametrize('attribute',['hidden','inert','aria-hidden="true"','style="display:none"','class="hidden-panel"'])
def test_excluded_ancestor_changes_are_bound_but_not_explanation(attribute):
    prefix='<h2 id="one">Question</h2><p>Actual explanation.</p>'
    panel='<pre>Raw source or log, not explanatory prose.</pre>'
    before=report(prefix+'<div>'+panel+'</div>')
    after=report(prefix+'<div '+attribute+'>'+panel+'</div>')
    old,new=before['items'][1],after['items'][1]
    assert old['body']==new['body']=='Actual explanation.'
    assert old['body_chars']==new['body_chars']
    assert old['excluded'][0]['sha256']==new['excluded'][0]['sha256']
    assert old['excluded'][0]['presentation_context']!=new['excluded'][0]['presentation_context']
    assert old['fingerprint']!=new['fingerprint']
    stale=apply_reviews(after,ledger(before))
    with pytest.raises(ValueError,match='incomplete'):
        enforce(stale)


def test_hidden_wrapper_changes_long_prose_and_figure_acceptance():
    original='<h2 id="one">Question</h2><div><p>'+('x'*601)+'</p>'+FIGURE+'</div>'
    before=report(original)
    after=report(original.replace('<div>','<div hidden>',1))
    accepted=ledger(before)
    for item in before['items']:
        if item['figures']:
            accepted['items'][item['id']].update(status='appropriate',figures=['states'])
    enforce(apply_reviews(before,accepted))
    assert before['items'][1]['body_chars']==after['items'][1]['body_chars']==601
    with pytest.raises(ValueError,match='incomplete'):
        enforce(apply_reviews(after,accepted))


def test_inline_hidden_word_is_visible_in_bound_presentation_context():
    before=report('<h2 id="one">Question</h2><p>Keep <span>buffers</span> valid.</p>')['items'][1]
    after=report('<h2 id="one">Question</h2><p>Keep <span hidden>buffers</span> valid.</p>')['items'][1]
    assert before['body']==after['body']
    assert before['fingerprint']!=after['fingerprint']
    assert any(value.get('text')=='buffers' and 'hidden' in value['path'][-1]['attrs']
               for value in after['presentation_contexts'].values())


@pytest.mark.parametrize('body',[
    '<details class="source-excerpts"><summary>Source evidence</summary><pre>Keep <span hidden>buffers</span> valid.</pre></details>',
    FIGURE.replace('</details>','<span hidden>Evidence qualification</span></details>'),
    '<div class="previous-route"><p>Old link <span hidden>qualification</span></p></div>',
])
def test_excluded_and_figure_evidence_descendant_presentation_is_bound(body):
    rows=report('<h2 id="one">Question</h2>'+body)['items']
    assert any('hidden' in value['path'][-1]['attrs']
               for row in rows for value in row['presentation_contexts'].values())


def test_next_sibling_wrapper_does_not_repin_unchanged_previous_item():
    before=report('<h2 id="one">One</h2><p>Stable explanation.</p><div><h2 id="two">Two</h2><p>Other.</p></div>')
    after=report('<h2 id="one">One</h2><p>Stable explanation.</p><div hidden><h2 id="two">Two</h2><p>Other.</p></div>')
    assert before['items'][1]['fingerprint']==after['items'][1]['fingerprint']
    assert before['items'][2]['fingerprint']!=after['items'][2]['fingerprint']


def test_article_and_body_presentation_are_bound():
    options=policy()
    original='<html><body><article><h2 id="one">Question</h2><p>Stable.</p></article></body></html>'
    first=inventory_page(original,'guide.html',options)[1]
    second=inventory_page(original.replace('<body>','<body hidden>'),'guide.html',options)[1]
    assert first['body']==second['body']
    assert first['fingerprint']!=second['fingerprint']


def test_standalone_media_and_figure_source_children_invalidate_current_context():
    original='<h2 id="one">One</h2><p>Explanation.</p><h2 id="two">Two</h2><p>Stable.</p>'
    before=report(original)
    after=report(original.replace('<h2 id="two">','<img alt="New illustration"><h2 id="two">'))
    assert before['items'][1]['fingerprint']!=after['items'][1]['fingerprint']
    # Inserting a sibling also moves the following question's bound position.
    assert before['items'][2]['fingerprint']!=after['items'][2]['fingerprint']
    changed=report(original.replace('<h2 id="two">','<img alt="Changed illustration"><h2 id="two">'))
    assert after['items'][1]['fingerprint']!=changed['items'][1]['fingerprint']
    assert after['items'][2]['fingerprint']==changed['items'][2]['fingerprint']
    hidden=FIGURE.replace('flowchart TB','<span hidden>flowchart TB</span>')
    rows=report('<h2 id="one">Question</h2>'+hidden)['items']
    assert any('hidden' in value['path'][-1]['attrs']
               for row in rows for value in row['presentation_contexts'].values())
    row=report('<h2 id="one">Question</h2><p><svg><text>Diagram</text></svg></p>')['items'][1]
    assert any(value['path'][-1]['tag']=='svg' for value in row['presentation_contexts'].values())


def test_hidden_parent_heading_invalidates_child_without_affecting_other_branch():
    before=report('<h2 id="one">One</h2><h3 id="child">Child</h3><p>Explanation.</p><h2 id="two">Two</h2><p>Stable.</p>')
    after=report('<h2 id="one" hidden>One</h2><h3 id="child">Child</h3><p>Explanation.</p><h2 id="two">Two</h2><p>Stable.</p>')
    assert before['items'][2]['fingerprint']!=after['items'][2]['fingerprint']
    assert before['items'][3]['fingerprint']==after['items'][3]['fingerprint']
    assert any('hidden' in element['attrs'] for value in after['items'][2]['presentation_contexts'].values()
               for element in value['path'])


def test_cited_window_parent_presentation_invalidates_owner_but_default_window_stays_compatible():
    from sdd.visual_audit import Document, source_window
    before='<h2 id="one">One</h2><p><a class="citation" href="#proof">Evidence</a></p><h2 id="two">Two</h2><div><p id="proof">Actual source.</p></div>'
    after=before.replace('<div>','<div hidden>')
    first,second=report(before),report(after)
    assert first['items'][1]['body']==second['items'][1]['body']
    assert first['items'][1]['fingerprint']!=second['items'][1]['fingerprint']
    a=Document('<article>'+before+'</article>');b=Document('<article>'+after+'</article>')
    assert source_window(a,'proof')==source_window(b,'proof')
    assert source_window(a,'proof',presentation=True)!=source_window(b,'proof',presentation=True)


def test_cited_source_heading_descendants_participate_in_presentation():
    from sdd.visual_audit import Document, source_window
    anchor='source-0123456789abcdef'
    before='<h2 id="one">One</h2><p><a class="citation" href="#'+anchor+'">Evidence</a></p><h2 id="'+anchor+'"><span>Source title</span></h2><details><summary>Source evidence</summary><pre>Code.</pre></details>'
    after=before.replace('<span>','<span hidden>')
    assert report(before)['items'][1]['fingerprint']!=report(after)['items'][1]['fingerprint']
    a=Document('<article>'+before+'</article>');b=Document('<article>'+after+'</article>')
    assert source_window(a,anchor)==source_window(b,anchor)
    assert source_window(a,anchor,presentation=True)!=source_window(b,anchor,presentation=True)


def test_subtree_context_retains_exact_leaf_text_without_ancestor_copies():
    row=report('<h2 id="one">Question</h2><p>Keep <b><span hidden>buffers</span></b> valid.</p>')['items'][1]
    texts=[v.get('text','') for v in row['presentation_contexts'].values()]
    assert texts.count('buffers')==1
    assert 'Keep  valid.' in texts


def test_cited_heading_cannot_move_text_to_hidden_descendant_without_invalidation():
    from sdd.visual_audit import Document, source_window
    before='<h2 id="one">One</h2><p><a class="citation" href="#proof">Evidence</a></p><h2 id="two"><span hidden>A</span><span>B</span></h2><p id="proof">Actual source.</p>'
    after=before.replace('<span hidden>A</span><span>B</span>','<span hidden>AB</span><span></span>')
    a=Document('<article>'+before+'</article>');b=Document('<article>'+after+'</article>')
    assert source_window(a,'proof')==source_window(b,'proof')
    assert source_window(a,'proof',presentation=True)!=source_window(b,'proof',presentation=True)
    assert report(before)['items'][1]['fingerprint']!=report(after)['items'][1]['fingerprint']


def test_loose_text_cannot_move_to_hidden_element_with_same_normalized_body():
    before='<h2 id="one">One</h2><div><p>Explanation.</p><span hidden>A</span><span>B C</span></div>'
    after=before.replace('<span hidden>A</span><span>B C</span>','<span hidden>A B</span><span>C</span>')
    a,b=report(before)['items'][1],report(after)['items'][1]
    assert a['body']==b['body']
    assert a['fingerprint']!=b['fingerprint']


@pytest.mark.parametrize('outside',[True,False])
def test_page_h1_presentation_is_inherited_by_independent_questions(outside):
    title='<h1><span>Page title</span></h1>'
    body='<h2 id="one">Question</h2><p>Explanation.</p>'
    source='<html><body>'+('<header>'+title+'</header><article>'+body if outside else '<article>'+title+body)+'</article></body></html>'
    before=next(row for row in inventory_page(source,'guide.html',policy()) if row['anchor']=='one')
    after=next(row for row in inventory_page(source.replace('<h1>','<h1 hidden>'),'guide.html',policy()) if row['anchor']=='one')
    assert before['body']==after['body']
    assert before['fingerprint']!=after['fingerprint']
    assert any('hidden' in element['attrs'] for value in after['presentation_contexts'].values()
               for element in value['path'])


def test_heading_repeated_siblings_preserve_order_and_multiplicity_in_child_context():
    before='<h2 id="one"><span>A</span><span>A</span><span hidden>B</span><span>B</span><span hidden>A</span><span hidden>B</span></h2><h3 id="child">Child</h3><p>Explanation.</p>'
    after='<h2 id="one"><span hidden>A</span><span>A</span><span>B</span><span hidden>B</span><span hidden>A</span><span>B</span></h2><h3 id="child">Child</h3><p>Explanation.</p>'
    a,b=report(before)['items'],report(after)['items']
    assert a[1]['title']==b[1]['title']=='AABBAB'
    assert a[1]['fingerprint']!=b[1]['fingerprint']
    assert a[2]['fingerprint']!=b[2]['fingerprint']


def test_heading_text_node_positions_preserve_line_break_placement():
    a=report('<h2 id="one">A<br>BC</h2><h3 id="child">Child</h3>')['items']
    b=report('<h2 id="one">AB<br>C</h2><h3 id="child">Child</h3>')['items']
    assert a[1]['title']==b[1]['title']=='ABC'
    assert a[2]['fingerprint']!=b[2]['fingerprint']


def test_hidden_nonvoid_self_closing_wrapper_cannot_disagree_with_browser_ancestry():
    row=report('<div hidden/><h2 id="one">Question</h2><p>Explanation.</p>')['items'][1]
    assert row['anchor']=='one'
    assert any('hidden' in element['attrs'] for value in row['presentation_contexts'].values()
               for element in value['path'])
    row=report('<svg><foreignObject><div hidden/><h2 id="one">Question</h2><p>Explanation.</p></div></foreignObject></svg>')['items'][1]
    assert any('hidden' in element['attrs'] for value in row['presentation_contexts'].values()
               for element in value['path'])
    assert report('<h2 id="one">Question</h2><svg><path d="M0 0"/></svg>')['items']


def test_excluded_source_heading_does_not_prevent_page_title_inheritance():
    source='<article><details class="source-excerpts"><h2>Raw heading</h2><pre>Code.</pre></details><h1>Page title</h1><h2 id="one">Question</h2><p>Explanation.</p></article>'
    a=next(row for row in inventory_page(source,'guide.html',policy()) if row['anchor']=='one')
    b=next(row for row in inventory_page(source.replace('<h1>','<h1 hidden>'),'guide.html',policy()) if row['anchor']=='one')
    assert a['anchor']==b['anchor']=='one'
    assert a['fingerprint']!=b['fingerprint']


def test_html5_implicit_paragraph_closure_preserves_independent_question():
    row=report('<p hidden>Intro<h2 id="one">Question</h2><p>Visible explanation.</p>')['items'][1]
    assert row['anchor']=='one'
    assert row['body']=='Visible explanation.'
    assert not any('hidden' in element['attrs'] for value in row['presentation_contexts'].values()
                   for element in value['path'])


def test_html5_implicit_list_closure_preserves_child_ownership():
    rows=report('<h2 id="one">Parent</h2><ul><li hidden>Old item<li><h3 id="child">Child</h3><p>Visible.</p></ul>')['items']
    child=next(row for row in rows if row['anchor']=='child')
    assert child['parent']=='guide.html#one'
    assert child['body']=='Visible.'
    assert not any('hidden' in element['attrs'] for value in child['presentation_contexts'].values()
                   for element in value['path'])


def test_text_after_nested_heading_is_bound_to_new_item_at_actual_position():
    a=report('<div><h2 id="one">Question</h2>A<br>B</div>')['items'][1]
    b=report('<div><h2 id="one">Question</h2>A B<br></div>')['items'][1]
    assert a['body']==b['body']=='A B'
    assert a['fingerprint']!=b['fingerprint']


def test_cited_window_inherits_real_heading_not_excluded_raw_heading():
    before='<h2 id="one">One</h2><p><a class="citation" href="#proof">Evidence</a></p><h2 id="two">Actual owner</h2><details class="source-excerpts"><h2>Raw heading</h2><pre>Other code.</pre></details><p id="proof">Actual source.</p>'
    after=before.replace('<h2 id="two">','<h2 id="two" hidden>')
    assert report(before)['items'][1]['fingerprint']!=report(after)['items'][1]['fingerprint']


def test_raw_source_heading_does_not_truncate_real_heading_window():
    from sdd.visual_audit import Document, source_window
    source='<article><h2 id="scope">Scope</h2><details class="source-excerpts"><h2>Raw heading</h2><pre>Raw code.</pre></details><p>Required following evidence.</p><h2 id="next">Next real section</h2></article>'
    window=source_window(Document(source),'scope',presentation=True)
    assert 'Raw code.' in window and 'Required following evidence.' in window
    assert 'Next real section' not in window


def test_real_page_title_is_not_replaced_by_excluded_raw_title_in_citation():
    from sdd.visual_audit import Document, source_window
    source='<h1>Actual title</h1><details class="source-excerpts"><h1>Raw title</h1><pre>Code.</pre></details><article><h2 id="one">Question</h2><p id="proof">Proof.</p></article>'
    changed=source.replace('<h1>Actual','<h1 hidden>Actual')
    assert source_window(Document(source),'proof')==source_window(Document(changed),'proof')
    assert source_window(Document(source),'proof',presentation=True)!=source_window(Document(changed),'proof',presentation=True)


def test_later_h1_starts_new_heading_context_for_following_questions():
    source='<h2 id="one">First</h2><p>Earlier explanation.</p><h1>New page title</h1><h2 id="two">Second</h2><p>Later explanation.</p>'
    a=report(source)['items'];b=report(source.replace('<h1>','<h1 hidden>'))['items']
    first=lambda rows: next(row for row in rows if row['anchor']=='one')
    second=lambda rows: next(row for row in rows if row['anchor']=='two')
    assert first(a)['fingerprint']==first(b)['fingerprint']
    assert second(a)['body']==second(b)['body']
    assert second(a)['fingerprint']!=second(b)['fingerprint']


@pytest.mark.parametrize('opening,closing',[('<div>','</div>'),('<ul><li>','</li></ul>'),
                                         ('<details><summary>','</summary></details>')])
def test_container_shortcuts_cannot_hide_wrapped_heading_transitions(opening,closing):
    source='<h2 id="one">First</h2>'+opening+'<h1>New title</h1>Intro'+closing+'<h2 id="next">Next question</h2><p>Explanation.</p>'
    a=report(source)['items'];b=report(source.replace('<h1>','<h1 hidden>'))['items']
    later=lambda rows:next(row for row in rows if row['anchor']=='next')
    assert later(a)['fingerprint']!=later(b)['fingerprint']
    question=report('<h2 id="one">Parent</h2>'+opening+'<h3 id="child">Independent question</h3>Answer.'+closing)['items']
    assert next(row for row in question if row['anchor']=='child')['body']=='Answer.'


def test_table_cell_heading_is_independent_and_owns_its_answer():
    rows=report('<h2 id="parent">Parent</h2><table><tr><td><h3 id="child">Independent question</h3><p>Its answer.</p></td></tr></table><h2 id="next">Next</h2><p>Other answer.</p>')['items']
    child=next(row for row in rows if row['anchor']=='child')
    assert child['parent']=='guide.html#parent'
    assert child['body']=='Its answer.'
    assert next(row for row in rows if row['anchor']=='next')['body']=='Other answer.'


@pytest.mark.parametrize('tag',['script','style'])
@pytest.mark.parametrize('opening,closing',[('<div>','</div>'),('<p>','</p>'),('<table><tr><td>','</td></tr></table>')])
def test_shortcuts_separate_nested_script_style_from_explanation(tag,opening,closing):
    row=report('<h2 id="one">Question</h2>'+opening+'<'+tag+'>Raw log only.</'+tag+'>'+closing)['items'][1]
    assert row['body']=='' and row['tables']==[]
    assert len(row['excluded'])==1 and row['excluded'][0]['kind']==tag


def test_multiple_prefix_titles_retain_the_content_and_presentation_they_own():
    source='<h1 id="first">First title</h1><p>First explanation.</p><h1 id="second">Second title</h1><p>Second explanation.</p><h2 id="one">Question</h2><p>Answer.</p>'
    a=report(source)['items'];b=report(source.replace('<h1 id="first">','<h1 id="first" hidden>'))['items']
    first=lambda rows:next(row for row in rows if row['anchor']=='first')
    second=lambda rows:next(row for row in rows if row['anchor']=='second')
    assert first(a)['body']=='First explanation.' and second(a)['body']=='Second explanation.'
    assert first(a)['fingerprint']!=first(b)['fingerprint']
    assert second(a)['fingerprint']==second(b)['fingerprint']


@pytest.mark.parametrize('tag',['script','style','pre'])
def test_source_log_container_inside_reader_heading_fails_without_hiding_scope(tag):
    with pytest.raises(ValueError,match='heading contains a source/log container'):
        report('<h2 id="one">Question<'+tag+'>Raw log.</'+tag+'></h2><p>Explanation.</p>')


def test_figure_owner_inherits_presentation_even_when_title_is_h2_sibling():
    graph=FIGURE.replace('<h3 id="figure">','<h2 id="figure">').replace('</h3>','</h2>')
    a=report('<h2 id="one">Question</h2><p>Explanation.</p><div>'+graph+'</div>')
    b=report('<h2 id="one">Question</h2><p>Explanation.</p><div hidden>'+graph+'</div>')
    owner=lambda value:next(row for row in value['items'] if row['anchor']=='one')
    assert owner(a)['children']==owner(b)['children']==[]
    assert owner(a)['fingerprint']!=owner(b)['fingerprint']
    assert any('hidden' in element['attrs'] for value in owner(b)['presentation_contexts'].values()
               for element in value['path'])


def test_duplicate_visibility_attributes_cannot_hide_the_browser_interpretation():
    with pytest.raises(ValueError,match='duplicate HTML attributes'):
        report('<h2 id="one">Question</h2><div style="display:none" style=""><p>Actual explanation.</p></div>')


def test_hidden_parent_after_review_preserves_last_good_site(tmp_cfg):
    import json
    from sdd.site_build import build_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    tmp_cfg.raw['visual_audit']=dict(enabled=True,reviews='reviews.json')
    content='<html><article><h2 id="one">Values</h2><div><table><tr><td>x</td></tr></table></div></article></html>'
    records=ledger(dict(items=inventory_page(content,'guide.html',policy(tmp_cfg))))
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(records),encoding='utf-8')
    def render(cfg,stage,mermaid):
        (stage/'guide.html').write_text(content,encoding='utf-8')
    destination=tmp_cfg.build_dir/'site'
    build_site(tmp_cfg,destination,render,None)
    before={p.relative_to(destination):p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    content=content.replace('<div>','<div hidden>')
    with pytest.raises(ValueError,match='incomplete'):
        build_site(tmp_cfg,destination,render,None)
    assert before=={p.relative_to(destination):p.read_bytes() for p in destination.rglob('*') if p.is_file()}
