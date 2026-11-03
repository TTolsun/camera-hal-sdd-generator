"""Fresh complete reviews cannot erase a previous reader question silently."""
import gzip
import hashlib
import json

import pytest

from sdd.facts.model import KnowledgeModel
from sdd.site_build import build_site, verify_site
from sdd.visual_audit import (REPORT, apply_reviews, baseline_contract, inspect_site,
                              policy, retain_baseline_items, enforce, verify_published)
from test_visual_audit import document, ledger, report


def save_baseline(cfg, result):
    raw = gzip.compress(json.dumps({**result,'schema':1,'source_commit':'a'*40}).encode(),mtime=0)
    path = cfg.root/'previous-items.json.gz'
    path.write_bytes(raw)
    cfg.raw['visual_audit'] = dict(enabled=True,reviews='reviews.json',
        baseline=dict(file=path.name,sha256=hashlib.sha256(raw).hexdigest()))
    return path


def test_fresh_ledger_cannot_delete_a_baseline_question(tmp_cfg):
    old = report('<h2 id="keep">Keep</h2><p>One value.</p><h2 id="required">Required</h2><p>A separate reader question.</p>')
    save_baseline(tmp_cfg,old)
    current = report('<h2 id="keep">Keep</h2><p>One value.</p>')
    enforce(apply_reviews(current,ledger(current)))
    retain_baseline_items(current,baseline_contract(tmp_cfg,policy(tmp_cfg)))
    with pytest.raises(ValueError,match='Baseline reader question deleted'):
        enforce(current)


def test_auxiliary_titles_can_change_but_questions_cannot_become_titles(tmp_cfg):
    old = report('<h2 id="keep">Keep</h2><p>A separate question.</p>')
    old['items'].append(dict(id='guide.html#old-caption',fingerprint='c'*64,role='visual_title'))
    save_baseline(tmp_cfg,old)
    current = report('<h2 id="keep">Keep</h2><p>Revised explanation.</p>')
    enforce(retain_baseline_items(apply_reviews(current,ledger(current)),baseline_contract(tmp_cfg,policy(tmp_cfg))))
    current['items'][1]['role']='visual_title'
    with pytest.raises(ValueError,match='replaced by a figure title'):
        enforce(retain_baseline_items(current,baseline_contract(tmp_cfg,policy(tmp_cfg))))


def test_pinned_baseline_bytes_cannot_change(tmp_cfg):
    path=save_baseline(tmp_cfg,report('<h2 id="keep">Keep</h2><p>Value.</p>'))
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='baseline digest changed'):
        baseline_contract(tmp_cfg,policy(tmp_cfg))


@pytest.mark.parametrize('title',['First question','Details'])
def test_positional_ids_cannot_shift_between_reader_questions(tmp_cfg,title):
    old=report('<h2>'+title+'</h2><p>First.</p><h2>Details</h2><p>Second.</p>')
    save_baseline(tmp_cfg,old)
    current=report('<h2>Second question</h2><p>Second.</p><h2>Third question</h2><p>Third.</p>')
    apply_reviews(current,ledger(current))
    with pytest.raises(ValueError,match='require persistent explicit anchors'):
        enforce(retain_baseline_items(current,baseline_contract(tmp_cfg,policy(tmp_cfg))))


@pytest.mark.parametrize('tag',['nav','aside','footer'])
def test_moving_question_into_chrome_cannot_satisfy_retention(tmp_cfg,tag):
    old=report('<h2 id="required">Required question</h2><p>Explanation.</p>')
    save_baseline(tmp_cfg,old)
    current=report('<'+tag+'><h2 id="required">Required question</h2><p>Explanation.</p></'+tag+'>')
    apply_reviews(current,ledger(current))
    assert all(row.get('anchor')!='required' for row in current['items'])
    with pytest.raises(ValueError,match='Baseline reader question deleted'):
        enforce(retain_baseline_items(current,baseline_contract(tmp_cfg,policy(tmp_cfg))))


@pytest.mark.parametrize('tag',['nav','aside','footer'])
def test_entire_article_inside_chrome_cannot_satisfy_retention(tmp_cfg,tag):
    from sdd.visual_audit import inventory_page
    html='<html><'+tag+'><article><h2 id="required">Required</h2></article></'+tag+'></html>'
    with pytest.raises(ValueError,match='exactly one readable article'):
        inventory_page(html,'guide.html',policy())


def test_multiple_readable_articles_cannot_hide_uninventoried_questions():
    from sdd.visual_audit import inventory_page
    html='<html><article><h2 id="first">First</h2></article><article><h2 id="other">Other</h2></article></html>'
    with pytest.raises(ValueError,match='exactly one readable article'):
        inventory_page(html,'guide.html',policy())


def test_deleted_question_preserves_previous_site_and_published_verifier_checks_it(tmp_cfg):
    KnowledgeModel(meta=dict(source_commit='a'*40)).save(tmp_cfg.facts_path)
    full='<h2 id="keep">Keep</h2><p>One value.</p><h2 id="required">Required</h2><p>Another value.</p>'
    bodies={'guide.html':document(full),'en/guide.html':document(full,'en')}
    def render(cfg,out,*args):
        for rel,text in bodies.items():
            path=out/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    original=tmp_cfg.root/'original-site';original.mkdir();render(tmp_cfg,original)
    baseline=inspect_site(original,policy(),source_commit='a'*40)
    save_baseline(tmp_cfg,baseline)
    current=inspect_site(original,policy(tmp_cfg),source_commit='a'*40)
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(ledger(current)),encoding='utf-8')
    out=tmp_cfg.root/'published'
    build_site(tmp_cfg,out,render,None)
    assert verify_site(out)['html_pages']==2
    manifest=json.loads((out/'site-manifest.json').read_bytes())
    assert manifest['inputs']['item_visual_baseline']
    assert manifest['inputs']['item_visual_retention']
    recorded=json.loads((out/REPORT).read_bytes())
    before={p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()}
    bodies={key:document('<h2 id="keep">Keep</h2><p>One value.</p>','en' if key.startswith('en/') else 'ko') for key in bodies}
    modified=tmp_cfg.root/'modified';modified.mkdir();render(tmp_cfg,modified)
    fresh=inspect_site(modified,policy(tmp_cfg),source_commit='a'*40)
    new_ledger=ledger(fresh)
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(new_ledger),encoding='utf-8')
    with pytest.raises(ValueError,match='Baseline reader question deleted'):
        build_site(tmp_cfg,out,render,None)
    assert before=={p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()}
    # Isolate published semantic verification from ordinary artifact checksums:
    # even new judgments for all remaining rows cannot drop the retained IDs.
    fresh=apply_reviews(fresh,new_ledger)
    fresh['baseline_retention']=recorded['baseline_retention']
    (modified/REPORT).write_text(json.dumps(fresh),encoding='utf-8')
    with pytest.raises(ValueError,match='Baseline reader question deleted'):
        verify_published(modified,dict(inputs=manifest['inputs'],outputs={rel:'fixture' for rel in [*bodies,REPORT]}))
    del fresh['baseline_retention']
    (modified/REPORT).write_text(json.dumps(fresh),encoding='utf-8')
    with pytest.raises(ValueError,match='retention contract missing or changed'):
        verify_published(modified,dict(inputs=manifest['inputs'],outputs={rel:'fixture' for rel in [*bodies,REPORT]}))
    # Self-reported baseline SHA cannot authenticate a weakened retained ID set.
    fresh['baseline_retention']=dict(recorded['baseline_retention'])
    fresh['baseline_retention']['required_items']={key:value for key,value in recorded['baseline_retention']['required_items'].items() if key in new_ledger['items']}
    (modified/REPORT).write_text(json.dumps(fresh),encoding='utf-8')
    with pytest.raises(ValueError,match='retention contract missing or changed'):
        verify_published(modified,dict(inputs=manifest['inputs'],outputs={rel:'fixture' for rel in [*bodies,REPORT]}))
    with pytest.raises(ValueError,match='requires its audit report'):
        verify_published(modified,dict(inputs=manifest['inputs'],outputs={}))
