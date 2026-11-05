"""Role figures keep actual source pins, item boundaries and publication rollback."""
from copy import deepcopy
import hashlib,json
import pytest
import yaml

from sdd.export_site import export_site
from sdd.site_build import verify_site
from sdd.reader_path_visuals import _position
from test_reader_paths import paths
from test_generated_design import generated


@pytest.fixture
def role_visual(tmp_cfg, paths):
    data, write_paths, section, model, _, _ = paths
    topic = section['design_topics'][0]
    evidence = model.evidence['device/stop/stop']
    pin = dict(source='stop/stop',sha256=evidence['sha256'],quote=evidence['text'].strip())
    graph = dict(id='role-stop',topic=topic['id'],kind='ownership',title='사용 주체와 종료 경계',
        question='종료 전후의 사용 경계는 무엇입니까?',
        nodes=[dict(id='owner',label='사용 주체',label_en='Owner',evidence=[pin]),
               dict(id='boundary',label='종료 경계',label_en='Stop boundary',evidence=[pin])],
        edges=[dict(**{'from':'owner','to':'boundary'},label='사용 경계를 확인',label_en='Check the use boundary',evidence=[pin])])
    registry=dict(schema=1,sections={'device':[graph]})
    data['visuals']=dict(file='reader-visuals.yaml',placements=[dict(role='work',anchor='claim-observed',section='device',visual='role-stop')])
    def write():
        write_paths()
        (tmp_cfg.root/'reader-visuals.yaml').write_text(yaml.safe_dump(registry,allow_unicode=True),encoding='utf-8')
    write()
    return data,registry,graph,write,model


def files(root):
    return {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_local_role_figure_uses_normal_source_and_download_without_changing_prose(tmp_cfg,role_visual):
    from sdd.site_localization import english_diagram
    from sdd.visual_audit import Document,plain
    data,registry,graph,write,model=role_visual
    before=(tmp_cfg.sdd_dir/'device.md').read_bytes()
    site=export_site(tmp_cfg)
    assert verify_site(site)['broken_links']==0
    page=(site/'reader-work.html').read_text(encoding='utf-8')
    assert 'device.html#source-' in page
    assert any(graph['title'] in plain(node) for node in Document(page).root.all('h4'))
    assert page.count('<!-- sdd:visual:role-stop -->')==1
    assert page.index('</blockquote>') < page.index('<!-- sdd:visual:role-stop -->')
    assert 'reader-work.role-stop.mmd' in page
    assert not (site/'reader-decision.role-stop.mmd').exists()
    source=(site/'reader-work.role-stop.mmd').read_text(encoding='utf-8')
    assert 'Owner' in english_diagram(source) and 'Stop boundary' in english_diagram(source)
    assert (tmp_cfg.sdd_dir/'device.md').read_bytes()==before
    manifest=(site/'site-manifest.json').read_bytes()
    assert json.loads(manifest)['inputs']['reader_path_visuals']==hashlib.sha256((tmp_cfg.root/'reader-visuals.yaml').read_bytes()).hexdigest()
    export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes()==manifest


@pytest.mark.parametrize('change',['missing-definition','missing-placement','missing-file','stale-omit','node-limit','unknown-anchor','wrong-source','repeated-target','repeated-across-roles','wrong-topic'])
def test_bad_role_figure_preserves_entire_last_good_site(tmp_cfg,role_visual,change):
    data,registry,graph,write,model=role_visual
    site=export_site(tmp_cfg);before=files(site)
    if change=='missing-definition':registry['sections']['device']=[]
    elif change=='missing-placement':data['visuals']['placements']=[]
    elif change=='missing-file':data['visuals']['file']='absent.yaml'
    elif change=='stale-omit':
        tmp_cfg.raw.setdefault('visuals',{})['on_stale']='omit'
        graph['nodes'][0]['evidence'][0]['sha256']='0'*64
    elif change=='node-limit':tmp_cfg.raw.setdefault('visuals',{})['max_nodes']=1
    elif change=='unknown-anchor':data['visuals']['placements'][0]['anchor']='claim-missing'
    elif change=='wrong-source':data['visuals']['placements'][0]['section']='missing'
    elif change=='repeated-target':data['visuals']['placements'].append(deepcopy(data['visuals']['placements'][0]))
    elif change=='repeated-across-roles':data['visuals']['placements'].append({**data['visuals']['placements'][0],'role':'decision'})
    elif change=='wrong-topic':graph['topic']='absent'
    write()
    with pytest.raises((ValueError,RuntimeError,FileNotFoundError)):
        export_site(tmp_cfg)
    assert files(site)==before


def test_position_keeps_numbered_procedure_and_its_continuation_together():
    body='## 조사 {#question-investigation}\n\n### 절차 {#claim-observed}\n\n1. 먼저 확인합니다.\n\n   설명을 이어 갑니다.\n\n2. 다음을 확인합니다.\n\n조건과 예외입니다.\n'
    position,level=_position(body,'question-investigation')
    assert level==3
    assert position>body.index('2. 다음을 확인합니다.') and position<body.index('조건과 예외입니다.')
    quoted='### 근거 {#claim-observed}\n\n> 1. 먼저 확인합니다.\n\n>    설명을 이어 갑니다.\n\n> 2. 다음을 확인합니다.\n\n> 조건과 예외입니다.\n'
    position,level=_position(quoted,'claim-observed')
    assert level==3
    assert position>quoted.index('> 2. 다음을 확인합니다.') and position<quoted.index('> 조건과 예외입니다.')
    with pytest.raises(ValueError,match='needs an explanation'):
        _position('## 조사 {#question-investigation}\n\n### 하위 질문\n','question-investigation')


def test_source_sections_cannot_collide_in_one_role_download(tmp_cfg,paths,role_visual):
    from sdd.reader_path_visuals import placements
    data,registry,graph,write,model=role_visual
    data['claims'][1]['sources'].append(dict(section='other',topic='stop'))
    data['visuals']['placements'].append(dict(role='work',anchor='claim-hypothesis',section='other',visual=graph['id']))
    registry['sections']['other']=[deepcopy(graph)]
    write()
    with pytest.raises(ValueError,match='output IDs must be unique'):
        placements(tmp_cfg,data,{'device.md':{'id':'device'},'other.md':{'id':'other'}})


def test_question_visual_follows_first_displayed_claim_explanation(tmp_cfg,role_visual):
    data,registry,graph,write,model=role_visual
    data['visuals']['placements'][0]['anchor']='question-investigation'
    write()
    site=export_site(tmp_cfg)
    assert verify_site(site)['broken_links']==0
    page=(site/'reader-work.html').read_text(encoding='utf-8')
    assert page.index('id="claim-observed"') < page.index('<!-- sdd:visual:role-stop -->') < page.index('id="claim-hypothesis"')


@pytest.mark.parametrize('change',['unrelated-claim-section','unrelated-claim-topic','unrelated-evidence-topic'])
def test_target_item_cannot_borrow_another_claims_source(tmp_cfg,role_visual,change):
    from sdd.reader_path_visuals import placements
    data,registry,graph,write,model=role_visual
    site=export_site(tmp_cfg);before=files(site)
    if change=='unrelated-claim-section':
        data['claims'][0]['sources'][0]['section']='other'
        sections={'device.md':{'id':'device'},'other.md':{'id':'other'}}
    else:
        data['claims'][0]['sources'][0]['topic']='other'
        sections={'device.md':{'id':'device'}}
        if change=='unrelated-evidence-topic':
            graph['topic']='other'
    write()
    with pytest.raises(ValueError,match='referenced canonical source|referenced by its target item|belong to its target item'):
        placements(tmp_cfg,data,sections)
    assert files(site)==before


def test_repeated_claim_link_cannot_be_used_as_question_explanation():
    body='## 調査 {#question-investigation}\n\n[同じ根拠](#claim-observed)\n\n## 次 {#question-verification}\n'
    with pytest.raises(ValueError,match='needs an explanation'):
        _position(body,'question-investigation')


def test_question_figure_cannot_borrow_a_later_claim_topic(tmp_cfg,role_visual):
    from sdd.reader_path_visuals import placements
    data,registry,graph,write,model=role_visual
    data['visuals']['placements'][0]['anchor']='question-investigation'
    data['claims'][0]['sources'][0]['topic']='first-only'
    write()
    with pytest.raises(ValueError,match='referenced by its target item'):
        placements(tmp_cfg,data,{'device.md':{'id':'device'}})


def test_question_and_claim_aliases_cannot_fill_the_same_item_twice(tmp_cfg,role_visual):
    data,registry,graph,write,model=role_visual
    site=export_site(tmp_cfg);before=files(site)
    other=deepcopy(graph);other['id']='another-stop'
    registry['sections']['device'].append(other)
    data['visuals']['placements'].append(dict(role='work',anchor='question-investigation',section='device',visual=other['id']))
    write()
    with pytest.raises(ValueError,match='one unique figure per placement'):
        export_site(tmp_cfg)
    assert files(site)==before
