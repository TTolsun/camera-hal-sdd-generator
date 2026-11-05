"""Rendered main includes the provenance question after the article."""
import json
import pytest
from sdd.visual_audit import Document,apply_reviews,enforce,inventory_page,policy,source_window
from test_visual_audit import ledger


def frame(meta=True,value='revision one',hidden=''):
    return ('<html lang="ko"><body><main><p class="breadcrumb">Route label</p><h1>Page title</h1>'
            '<div class="page-state">Pending badge</div><details class="mobile-toc"><summary>TOC control</summary>'
            '<nav><h2>Navigation control</h2></nav></details><article><h2 id="question">Question</h2>'
            '<p>Actual explanation.</p></article>'+(
            '<section class="evidence" '+hidden+'><h2 id="page-evidence">Generation and review</h2>'
            '<dl><dt>Source</dt><dd>'+value+'</dd></dl></section>' if meta else '')+
            '<nav><h2>Pagination control</h2></nav><footer>Generated footer</footer></main>'
            '<dialog><h2 id="search-title">Search control</h2></dialog></body></html>')


def report(source):
    return dict(items=inventory_page(source,'guide.html',policy()),policy=policy(),errors=[])


def item(result,anchor):
    return next(row for row in result['items'] if row['anchor']==anchor)


def test_provenance_h2_is_inventoried_without_counting_shell_controls():
    result=report(frame())
    assert [row['anchor'] for row in result['items']]==[None,'question','page-evidence']
    assert item(result,'question')['body']=='Actual explanation.'
    assert 'revision one' in item(result,'page-evidence')['body']
    assert not any('control' in row['body'] or 'Route label' in row['body'] or 'Pending badge' in row['body']
                   for row in result['items'])


def test_new_metadata_item_cannot_reuse_an_article_only_ledger():
    before=report(frame(meta=False));after=report(frame())
    assert item(before,'question')['fingerprint']==item(after,'question')['fingerprint']
    with pytest.raises(ValueError,match='incomplete'):
        enforce(apply_reviews(after,ledger(before)))


def test_metadata_changes_invalidate_its_review_without_repinning_article():
    before=report(frame());after=report(frame(value='revision two'))
    assert item(before,'question')['fingerprint']==item(after,'question')['fingerprint']
    assert item(before,'page-evidence')['fingerprint']!=item(after,'page-evidence')['fingerprint']
    with pytest.raises(ValueError,match='incomplete'):
        enforce(apply_reviews(after,ledger(before)))


def test_hidden_metadata_ancestor_is_bound_and_window_is_main_scoped():
    before=report(frame());after=report(frame(hidden='hidden'))
    assert item(before,'page-evidence')['body']==item(after,'page-evidence')['body']
    assert item(before,'page-evidence')['fingerprint']!=item(after,'page-evidence')['fingerprint']
    window=source_window(Document(frame()),'page-evidence',presentation=True)
    assert 'revision one' in window and 'Actual explanation.' not in window


def test_excluded_metadata_log_is_not_explanatory_prose():
    source=frame().replace('</dl>','</dl><details class="manuscript-record"><summary>Old generation record</summary><pre>Raw historical log.</pre></details>')
    record=item(report(source),'page-evidence')
    assert 'Raw historical log.' not in record['body']
    assert len(record['excluded'])==1 and record['excluded'][0]['kind']=='details'


def test_main_layout_is_unambiguous_and_control_cannot_swallow_reader_heading():
    with pytest.raises(ValueError,match='one main'):
        report(frame().replace('</body>','<main><h2>Lost question</h2></main></body>'))
    with pytest.raises(ValueError,match='heading inside generated shell control'):
        report(frame().replace('Pending badge','<h2>Unexpected reader question</h2>'))
    with pytest.raises(ValueError,match='question inside generated page title'):
        report(frame().replace('Page title</h1>','Page title<svg><foreignObject><h2>Unexpected reader question</h2></foreignObject></svg></h1>'))


def test_missing_metadata_review_preserves_last_good_site(tmp_cfg):
    from sdd.site_build import build_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    tmp_cfg.raw['visual_audit']=dict(enabled=True,reviews='reviews.json')
    source=frame(meta=False)
    records=ledger(dict(items=inventory_page(source,'guide.html',policy(tmp_cfg))))
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(records),encoding='utf-8')
    def render(cfg,stage,mermaid):(stage/'guide.html').write_text(source,encoding='utf-8')
    target=tmp_cfg.build_dir/'site';build_site(tmp_cfg,target,render,None)
    original={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
    source=frame()
    with pytest.raises(ValueError,match='incomplete'):
        build_site(tmp_cfg,target,render,None)
    assert original=={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}


def test_required_provenance_cannot_disappear_with_its_review(tmp_cfg):
    from sdd.site_build import build_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    tmp_cfg.raw['visual_audit']=dict(enabled=True,reviews='reviews.json',require_provenance=True)
    source=frame()
    records=ledger(dict(items=inventory_page(source,'guide.html',policy(tmp_cfg))))
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(records),encoding='utf-8')
    def render(cfg,stage,mermaid):(stage/'guide.html').write_text(source,encoding='utf-8')
    target=tmp_cfg.build_dir/'site';build_site(tmp_cfg,target,render,None)
    original={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
    source=frame(meta=False)
    with pytest.raises(ValueError,match='requires one generated provenance section'):
        build_site(tmp_cfg,target,render,None)
    assert original=={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
    # Removing the review as well must not conceal removal of the entire H2.
    with pytest.raises(ValueError,match='requires one generated provenance section'):
        inventory_page(source,'guide.html',policy(tmp_cfg))
    source=source.replace('<main>','').replace('</main>','')
    with pytest.raises(ValueError,match='requires one main and generated provenance section'):
        inventory_page(source,'guide.html',policy(tmp_cfg))
    with pytest.raises(ValueError,match='requires one main and generated provenance section'):
        build_site(tmp_cfg,target,render,None)
    assert original=={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}


def test_required_provenance_is_a_boolean_and_keeps_standalone_drafts_usable(tmp_cfg):
    tmp_cfg.raw['visual_audit']={'require_provenance':'true'}
    with pytest.raises(ValueError,match='require_provenance must be boolean'):
        policy(tmp_cfg)
    tmp_cfg.raw['visual_audit']={'require_provenance':True}
    options=policy(tmp_cfg)
    assert inventory_page('<article><h2 id="q">Question</h2><p>Draft.</p></article>','draft.html',options,draft=True)
    with pytest.raises(ValueError,match='requires one generated provenance section'):
        inventory_page(frame().replace('class="evidence"','class="other"'),'guide.html',options)
    with pytest.raises(ValueError,match='requires one generated provenance section'):
        inventory_page(frame().replace('</article>','<h2 id="page-evidence">Fake</h2></article>').replace('class="evidence"','class="other"'),'guide.html',options)
