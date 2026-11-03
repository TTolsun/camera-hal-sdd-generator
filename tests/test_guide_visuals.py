"""Reading maps are separate document evidence, with normal publication rollback."""
import copy
import hashlib
import json
import subprocess

import pytest
import yaml

from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.site_localization import english_diagram, KOREAN
from sdd.guide_visuals import inject, headings

from test_design_contracts import contract
from test_generated_design import generated
from test_visuals import visual


@pytest.fixture
def guide(tmp_cfg, visual):
    _, model, graph, _ = visual
    intro = '# Guide\n\n## Reading order\n\n1. First read cancelPending();\n2. Follow the request.\n3. Find the diagnosis.\n\nCheck the conditions before editing.\n\n## Other\n\nOther question.\n'
    (tmp_cfg.root/'intro.md').write_text(intro,encoding='utf-8',newline='\n')
    origin = tmp_cfg.root/'guide-source'
    origin.mkdir()
    (origin/'intro.md').write_bytes(intro.encode())
    git = ['git','-c','core.hooksPath='+str(origin/'empty-hooks'),'-c','commit.gpgsign=false']
    for args in [['init','-q'],['config','user.name','Synthetic guide'],
                 ['config','user.email','fixture@example.invalid'],['add','intro.md'],['commit','-qm','Synthetic guide']]:
        subprocess.run(git+args,cwd=origin,check=True,capture_output=True)
    commit = subprocess.check_output(git+['rev-parse','HEAD'],cwd=origin,text=True).strip()
    graph = copy.deepcopy(graph)
    graph.update(id='reading-route',topic='guide',title='읽는 순서',question='어떤 순서로 문서를 읽습니까?')
    for element in [*graph['nodes'],*graph['edges']]:
        element['evidence']=[dict(source='guide/intro',sha256=hashlib.sha256(intro.encode()).hexdigest(),quote='cancelPending();')]
    data = dict(schema=1,source=dict(file='intro.md',sha256=hashlib.sha256(intro.encode()).hexdigest(),commit=commit),
                figures=[dict(heading='Reading order',visual=graph)])
    tmp_cfg.raw.setdefault('site',{}).update(intro='intro.md',guide_visuals='guide.json',guide_source=dict(root='guide-source',file='intro.md'))
    def save():
        (tmp_cfg.root/'guide.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    save()
    return intro,data,model,save


def test_numbered_procedure_and_existing_other_question_visual_are_preserved(tmp_cfg, guide):
    intro,data,_,_ = guide
    other = '<!-- sdd:visual:other -->\n### Other map\n\nother\n<!-- /sdd:visual:other -->'
    body, rendered = inject(tmp_cfg,intro+'\n'+other,{'other'})
    assert body.index('3. Find the diagnosis.') < body.index('### 읽는 순서') < body.index('Check the conditions')
    assert other in body and len(rendered) == 1
    assert '안내 문서 커밋: <code>'+data['source']['commit'] in body
    assert '라이브러리의 실행 순서나 기기 검증을 뜻하지 않습니다' in body
    assert 'source-' in body and '<pre><code>' in body
    assert not KOREAN.search(english_diagram(rendered[0][2]))


def test_fenced_and_raw_code_headings_cannot_replace_real_guide_questions():
    body = '````markdown\n## Fenced\n\nexample\n````\n\n<pre><code>\n## Raw\n\nexample\n</code></pre>\n\n## Actual\n\nRead here.\n'
    assert [match[1] for match in headings(body)] == ['Actual']


def test_even_trailing_prose_whitespace_cannot_change_the_reviewed_guide(tmp_cfg, guide):
    intro,_,_,_ = guide
    with pytest.raises(ValueError,match='differs'):
        inject(tmp_cfg,intro.replace('before editing.\n','before editing.  \n'),set())


@pytest.mark.parametrize('change',['source','revision','quote','heading','limit','collision','rendered'])
def test_required_guide_failure_preserves_the_previous_site(tmp_cfg, guide, change):
    intro,data,model,save = guide
    Generator(tmp_cfg,model,None).run()
    site = export_site(tmp_cfg)
    before = {p.relative_to(site):p.read_bytes() for p in site.rglob('*') if p.is_file()}
    manifest = json.loads(before[next(p for p in before if p.as_posix()=='site-manifest.json')])
    assert manifest['inputs']['guide_visuals']
    assert (site/'index.reading-route.mmd').is_file()
    document = (site/'index.html').read_text(encoding='utf-8')
    import re
    assert re.search(r'<p><a id="source-[0-9a-f]{16}"></a></p>\s*<details data-sdd-guide-source="true">',document)
    if change == 'source':
        (tmp_cfg.root/'intro.md').write_text(intro+'changed\n',encoding='utf-8')
    elif change == 'revision':
        changed = (intro+'changed\n').encode()
        (tmp_cfg.root/'intro.md').write_bytes(changed)
        data['source']['sha256'] = hashlib.sha256(changed).hexdigest()
        save()
    elif change == 'quote':
        data['figures'][0]['visual']['nodes'][0]['evidence'][0]['quote']='Other question.'
        save()
    elif change == 'heading':
        data['figures'][0]['heading']='Missing'
        save()
    elif change == 'limit':
        tmp_cfg.raw['visuals']['max_nodes']=1
    elif change == 'rendered':
        (tmp_cfg.sdd_dir/'index.md').write_text(intro.replace('Find the diagnosis.','Unrelated manuscript.'),encoding='utf-8')
        sections = yaml.safe_load(tmp_cfg.sections_file.read_bytes())
        sections['sections'].append(dict(id='guide-index',title='Guide',kind='manual',output='index.md'))
        tmp_cfg.sections_file.write_text(yaml.safe_dump(sections,allow_unicode=True),encoding='utf-8')
        navigation = dict(nav=[{'Guide':'index.md'},{'Device':'device.md'}])
        (tmp_cfg.root/'mkdocs.yml').write_text(yaml.safe_dump(navigation),encoding='utf-8')
    else:
        tmp_cfg.raw['site']['overview_visual']=dict(section='device',visual='reading-route')
    tmp_cfg.raw['visuals']['on_stale']='omit'
    with pytest.raises(ValueError):
        export_site(tmp_cfg)
    assert before == {p.relative_to(site):p.read_bytes() for p in site.rglob('*') if p.is_file()}
