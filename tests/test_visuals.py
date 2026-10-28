import copy

import pytest
import yaml

from sdd.visuals import render, place
from sdd.site_localization import english_diagram
from sdd.export_site import export_site
from sdd.generate import Generator


@pytest.fixture
def visual(tmp_cfg, contract):
    section, model, save = contract
    evidence = dict(source='shutdown/stop', sha256=model.evidence['device/shutdown/stop']['sha256'],
                    quote='cancelPending();')
    graph = dict(id='stop-flow', topic='shutdown', kind='decision', title='종료의 분기', question='대기 요청은 어떻게 끝납니까?',
                 nodes=[dict(id='pending', label='대기 요청', label_en='Pending requests', evidence=[evidence]),
                        dict(id='cancelled', label='취소됨', label_en='Cancelled', evidence=[evidence])],
                 edges=[dict(**{'from': 'pending', 'to': 'cancelled'}, label='stop()으로 취소',
                             label_en='cancelled by stop()', evidence=[evidence])])
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    def write():
        (tmp_cfg.root / 'visuals.yaml').write_text(yaml.safe_dump(dict(schema=1, sections={'device': [graph]}),
                                                               allow_unicode=True), encoding='utf-8')
        save()
    write()
    return section, model, graph, write


# Reuse the source-bound fixture so both prose and diagrams must pass the same source pins.
from test_design_contracts import contract
from test_generated_design import generated


def test_index_reuses_a_source_bound_visual_without_changing_its_definition(tmp_cfg, visual):
    import json
    section, model, graph, write = visual
    tmp_cfg.raw.setdefault('site', {})['overview_visual'] = dict(section='device', visual='stop-flow')
    Generator(tmp_cfg, model, None).run()
    site = export_site(tmp_cfg)
    before = (site/'site-manifest.json').read_bytes()
    index = (site/'index.html').read_text(encoding='utf-8')
    assert '종료의 분기' in index and '대기 요청은 어떻게 끝납니까?' in index
    assert 'href="index.stop-flow.mmd"' in index
    assert 'device.html#source-' in index and 'href="#source-' not in index
    assert (site/'index.stop-flow.mmd').read_bytes() == (site/'device.stop-flow.mmd').read_bytes()
    export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes() == before
    assert json.loads(before)['outputs']['index.stop-flow.mmd']
    tmp_cfg.raw['visuals']['on_stale'] = 'omit'
    graph['nodes'][0]['evidence'][0]['sha256'] = '0'*64
    write()
    with pytest.raises(ValueError):
        export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes() == before


@pytest.mark.parametrize('selection', [dict(section='missing', visual='stop-flow'),
                                      dict(section='device', visual='missing'),
                                      dict(section='device', visual='stop-flow', unknown=True)])
def test_index_reuse_rejects_missing_or_invalid_selection(tmp_cfg, visual, selection):
    _, model, _, _ = visual
    Generator(tmp_cfg, model, None).run()
    tmp_cfg.raw.setdefault('site', {})['overview_visual'] = selection
    with pytest.raises(ValueError):
        export_site(tmp_cfg)


@pytest.mark.parametrize('collision', [False, True])
def test_overview_preserves_existing_index_visuals_and_authorship(tmp_cfg, visual, collision):
    from sdd.document_metadata import split_frontmatter
    from sdd.export_site import _prepare_page_body
    section, model, graph, _ = visual
    own = {**copy.deepcopy(section), 'id': 'index-page', 'output': 'index.md', 'title': '별도 작성한 인덱스'}
    own_graph = {**copy.deepcopy(graph), 'id': graph['id'] if collision else 'own-flow', 'title': '원래 인덱스 그림'}
    model.evidence['index-page/shutdown/stop'] = copy.deepcopy(model.evidence['device/shutdown/stop'])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section, own]}, allow_unicode=True), encoding='utf-8')
    (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(dict(schema=1, sections={'device': [graph], 'index-page': [own_graph]}), allow_unicode=True), encoding='utf-8')
    model.save(tmp_cfg.facts_path)
    Generator(tmp_cfg, model, None).run()
    tmp_cfg.raw.setdefault('site', {})['overview_visual'] = dict(section='device', visual=graph['id'])
    if collision:
        with pytest.raises(ValueError, match='conflicts'):
            export_site(tmp_cfg)
        return
    site = export_site(tmp_cfg)
    assert (site/'index.own-flow.mmd').is_file() and (site/'index.stop-flow.mmd').is_file()
    html = (site/'index.html').read_text(encoding='utf-8')
    assert 'index.own-flow.mmd' in html and 'index.stop-flow.mmd' in html
    texts = {name: (tmp_cfg.sdd_dir/name).read_text(encoding='utf-8') for name in ['index.md','device.md']}
    before, _ = split_frontmatter(texts['index.md'])
    _, after, _, _, rendered = _prepare_page_body(tmp_cfg, 'index.md', texts, {'index.md': own, 'device.md': section}, [], model)
    assert before == after and len(rendered) == 2


def test_opt_in_omits_stale_interpretation_and_removes_old_download(tmp_cfg, visual):
    section, model, graph, write = visual
    Generator(tmp_cfg, model, None).run()
    site = export_site(tmp_cfg)
    assert (site/'device.stop-flow.mmd').exists()
    tmp_cfg.raw['visuals']['on_stale'] = 'omit'
    graph['nodes'][0]['evidence'][0]['sha256'] = '0' * 64
    write()
    result = render(tmp_cfg, model, section)
    assert result[0][2] == ''
    assert '재검토가 필요' in result[0][1]
    assert '```mermaid' not in result[0][1]
    export_site(tmp_cfg)
    assert not (site/'device.stop-flow.mmd').exists()
    html = (site/'device.html').read_text(encoding='utf-8')
    assert '재검토가 필요' in html
    assert 'href="device.stop-flow.mmd"' not in html


@pytest.mark.parametrize('invalid', ['commit', 'limit', 'edge'])
def test_stale_omission_does_not_bypass_structural_or_commit_checks(tmp_cfg, visual, invalid):
    section, model, graph, write = visual
    tmp_cfg.raw['visuals']['on_stale'] = 'omit'
    graph['nodes'][0]['evidence'][0]['sha256'] = '0' * 64
    if invalid == 'commit':
        model.meta['source_commit'] = 'b' * 40
    elif invalid == 'limit':
        tmp_cfg.raw['visuals']['max_nodes'] = 1
    else:
        graph['edges'][0]['to'] = 'missing'
    write()
    with pytest.raises(ValueError):
        render(tmp_cfg, model, section)


def test_diagrams_stay_near_explanation_in_markdown_html_and_english(tmp_cfg, visual):
    section, model, graph, _ = visual
    Generator(tmp_cfg, model, None).run()
    text = (tmp_cfg.sdd_dir / 'device.md').read_text(encoding='utf-8')
    assert text.index('stop()은 대기 요청을 취소합니다.') < text.index('### 종료의 분기') < text.index('## 소스 근거')
    assert text.count('<!-- sdd:visual:stop-flow -->') == 1
    site = export_site(tmp_cfg)
    document = (site / 'device.html').read_text(encoding='utf-8')
    assert document.count('<pre class="mermaid">') == 1
    assert '그림 근거와 확인 범위' in document and 'source-' in document
    assert 'href="device.stop-flow.mmd"' in document
    source = (site / 'device.stop-flow.mmd').read_text(encoding='utf-8')
    english = english_diagram(source)
    assert 'Pending requests' in english and '대기 요청' not in english
    assert 'v_pending -->|"cancelled by stop()"| v_cancelled' in english
    manifest = (site / 'site-manifest.json').read_bytes()
    export_site(tmp_cfg)
    assert (site / 'site-manifest.json').read_bytes() == manifest


@pytest.mark.parametrize('mutation', ['hash', 'text', 'quote', 'commit', 'missing-evidence', 'target', 'limit',
                                     'unknown-topic', 'duplicate-node', 'unsafe-id', 'missing-translation', 'selector'])
def test_invalid_diagrams_preserve_manuscripts_and_published_site(tmp_cfg, visual, mutation):
    section, model, graph, write = visual
    Generator(tmp_cfg, model, None).run()
    site = export_site(tmp_cfg)
    old = (site / 'site-manifest.json').read_bytes()
    manuscript = (tmp_cfg.sdd_dir / 'device.md').read_bytes()
    if mutation == 'hash': graph['edges'][0]['evidence'][0]['sha256'] = '0' * 64
    elif mutation == 'text': model.evidence['device/shutdown/stop']['text'] = 'changed code'
    elif mutation == 'quote': graph['edges'][0]['evidence'][0]['quote'] = 'invented();'
    elif mutation == 'commit': model.evidence['device/shutdown/stop']['commit'] = 'b' * 40
    elif mutation == 'missing-evidence': graph['nodes'][0]['evidence'] = []
    elif mutation == 'target': graph['edges'][0]['to'] = 'unknown'
    elif mutation == 'limit': tmp_cfg.raw['visuals']['max_nodes'] = 1
    elif mutation == 'unknown-topic': graph['topic'] = 'unknown'
    elif mutation == 'duplicate-node': graph['nodes'].append(copy.deepcopy(graph['nodes'][0]))
    elif mutation == 'unsafe-id': graph['nodes'][0]['id'] = 'x\nclick x javascript:evil'
    elif mutation == 'missing-translation': graph['nodes'][0].pop('label_en')
    elif mutation == 'selector': model.evidence['device/shutdown/stop']['selector']['end'] = 'new end'
    write()
    with pytest.raises(ValueError): Generator(tmp_cfg, model, None).run()
    assert (tmp_cfg.sdd_dir / 'device.md').read_bytes() == manuscript
    with pytest.raises((ValueError, RuntimeError)): export_site(tmp_cfg)
    assert (site / 'site-manifest.json').read_bytes() == old


def test_replaces_changed_edges_and_removes_deleted_diagrams(tmp_cfg, visual):
    section, model, graph, write = visual
    Generator(tmp_cfg, model, None).run()
    original = (tmp_cfg.sdd_dir / 'device.md').read_text(encoding='utf-8')
    graph['edges'][0]['label'] = '취소 경로'
    write()
    rendered = render(tmp_cfg, model, section)
    updated = place(original, rendered, section)
    assert updated.count('```mermaid') == 1 and 'stop()으로 취소' not in updated
    assert place(updated, rendered, section) == updated
    site = export_site(tmp_cfg)
    assert '취소 경로' in (site / 'device.html').read_text(encoding='utf-8')
    tmp_cfg.raw.pop('visuals')
    export_site(tmp_cfg)
    assert not (site / 'device.stop-flow.mmd').exists()
    assert '종료의 분기' not in (site / 'device.html').read_text(encoding='utf-8')


def test_stale_first_reference_cannot_hide_invalid_later_reference(tmp_cfg, visual):
    section, model, graph, write = visual
    tmp_cfg.raw['visuals']['on_stale'] = 'omit'
    refs = graph['nodes'][0]['evidence']
    invalid = copy.deepcopy(refs[0])
    refs[0]['sha256'] = '0' * 64
    invalid['source'] = 'missing/source'
    refs.append(invalid)
    write()
    with pytest.raises(ValueError, match='missing/source'):
        render(tmp_cfg, model, section)


def test_missing_heading_and_unsafe_labels(tmp_cfg, visual):
    section, model, graph, write = visual
    with pytest.raises(ValueError, match='heading'): place('# Missing\n', render(tmp_cfg, model, section), section)
    graph['nodes'][0]['label'] = '"><script>alert(1)</script>'
    write()
    _, block, source = render(tmp_cfg, model, section)[0]
    assert '<script>' not in block and '&lt;script&gt;' in source


def test_procedure_numbering_survives_nearby_visual(tmp_cfg, visual):
    from sdd.visuals import strip_blocks
    section, model, _, _ = visual
    body = '## 종료 계약\n\n1. 첫 단계입니다.\n\n2. 다음 단계입니다.\n\n## 소스 근거\n'
    updated = place(body, render(tmp_cfg, model, section), section)
    assert updated.index('### 종료의 분기') < updated.index('1. 첫 단계')
    assert strip_blocks(updated) == body


def test_generated_answer_integrity_and_review_are_preserved(tmp_cfg, generated):
    from sdd.generated_design import verify
    section, model, save, agent = generated
    evidence = dict(source='stop/stop', sha256=model.evidence['device/stop/stop']['sha256'], quote='cancelPending();')
    graph = dict(id='stop-flow', topic='stop', kind='flow', title='취소 경로', question='종료는 어디서 시작합니까?',
                 nodes=[dict(id='stop', label='stop()', label_en='stop()', evidence=[evidence]),
                        dict(id='cancel', label='cancelPending()', label_en='cancelPending()', evidence=[evidence])],
                 edges=[dict(**{'from':'stop','to':'cancel'}, label='호출', label_en='calls', evidence=[evidence])])
    tmp_cfg.raw['visuals'] = {'file': 'visuals.yaml'}
    (tmp_cfg.root / 'visuals.yaml').write_text(yaml.safe_dump(dict(schema=1, sections={'device':[graph]}), allow_unicode=True), encoding='utf-8')
    path = Generator(tmp_cfg, model, agent).run()[0]
    manuscript = path.read_text(encoding='utf-8')
    assert verify(model, section, manuscript)['human_review'] == 'pending'
    export_site(tmp_cfg)
    with pytest.raises(ValueError, match='원고 본문'):
        verify(model, section, manuscript.replace('종료는 어디서 시작합니까?', '다른 질문'))
