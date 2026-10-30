import copy
import hashlib
import json

import pytest
import yaml

from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.generated_visuals import from_manuscript
from sdd.carryover import carry_forward
from sdd.export_html import _split
from test_design_contracts import contract


@pytest.mark.parametrize('previous,anchor,target', [
    ('camera-model', '요청과-버퍼를-유지할-기간', 'camera-requests'),
    ('request-lifecycle', '요청이-대기하거나-장치로-가는-조건', 'request-diagnosis'),
    ('request-lifecycle', '구성-실패를-좁히는-분기', 'request-diagnosis'),
    ('pipeline-handler', '요청이-대기하거나-장치로-가는-조건', 'pipeline-requests'),
    ('pipeline-handler', '버퍼-완료에서-요청-반환까지', 'pipeline-requests'),
    ('ipu3-lsc-flow', 'lsc-파라미터를-갱신하는-분기', 'ipu3-lsc-prepare'),
])
def test_published_figure_deep_links_follow_the_moved_evidence(previous, anchor, target):
    from pathlib import Path
    from sdd.markdown_text import slugify
    root = Path(__file__).resolve().parents[1]/'examples/libcamera/config'
    sections = {s['id']: s for s in yaml.safe_load((root/'sections.yaml').read_text(encoding='utf-8'))['sections']}
    figures = yaml.safe_load((root/'visuals.yaml').read_text(encoding='utf-8'))['sections']
    links = [r for r in sections[previous]['routes'] if r.get('anchor') == anchor]
    assert len(links) == 1
    assert links[0]['to'] == sections[target]['output']+'#'+anchor
    moved = [v for v in figures[target] if slugify(v['title']) == anchor]
    assert len(moved) == 1
    assert moved[0]['topic'] in {t['id'] for t in sections[target]['design_topics']}


@pytest.fixture
def automatic(tmp_cfg, contract):
    section, model, save = contract
    plan = dict(id='stop-flow', topic='shutdown', kind='flow', generation='llm',
                title='종료와 취소', question='stop()과 cancelPending()의 연결은 무엇입니까?')
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.agent.max_input_chars = 20000
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    (tmp_cfg.root / 'visuals.yaml').write_text(yaml.safe_dump(dict(schema=1, sections={'device':[plan]}), allow_unicode=True), encoding='utf-8')
    draft = dict(nodes=[dict(id='stop', symbol='stop', label='stop()', label_en='stop()', shape='box', quote_ids=['stop:0']),
                        dict(id='cancel', symbol='cancelPending', label='취소 호출', label_en='Cancel pending', shape='box', quote_ids=['stop:0'])],
                 edges=[dict(**{'from':'stop','to':'cancel'},label='대기 요청 취소',label_en='Cancel waiting requests', condition_ref='always',quote_ids=['stop:0'])])
    class Agent:
        def __init__(self): self.calls=[]; self.draft=copy.deepcopy(draft)
        def chat(self, system, user, **kw): self.calls.append((system,user,kw)); return json.dumps(self.draft,ensure_ascii=False)
    return section, model, save, Agent()


def test_automatic_graph_generation_reuse_export_and_carryover(tmp_cfg, automatic):
    section, model, save, agent = automatic
    path=Generator(tmp_cfg,model,agent).run()[0]
    text=path.read_text(encoding='utf-8')
    assert len(agent.calls)==1 and 'response_schema' in agent.calls[0][2]
    assert 'LLM 그림 초안' in text and 'ollama/' in text
    assert 'sdd:visual:stop-flow' in text
    from_manuscript(tmp_cfg,model,section,text)
    Generator(tmp_cfg,model,agent).run()
    assert len(agent.calls)==1
    site=export_site(tmp_cfg)
    assert 'stop-flow.mmd' in (site/'device.html').read_text(encoding='utf-8')
    model.meta['source_commit']='b'*40
    model.evidence['device/shutdown/stop']['commit']='b'*40
    save()
    promoted,stale=carry_forward(tmp_cfg,model,[])
    assert promoted==[path] and not stale
    export_site(tmp_cfg)
    assert _split(path.read_text(encoding='utf-8'))[0]['generated_visuals']['records']['stop-flow']['generation_commit']=='a'*40


def test_visual_retry_supplies_rejected_draft_and_current_evidence(tmp_cfg, automatic):
    _, model, _, original = automatic
    good = json.dumps(original.draft, ensure_ascii=False)
    bad = copy.deepcopy(original.draft)
    bad['edges'][0]['quote_ids'] = ['missing:9']
    rejected = json.dumps(bad, ensure_ascii=False)
    class RepairingAgent:
        def __init__(self): self.calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return rejected
            assert rejected in user and 'missing:9' in user
            assert 'Current source inputs:' in user and 'stop:0' in user
            return good
    agent = RepairingAgent()
    paths = Generator(tmp_cfg, model, agent).run()
    assert agent.calls == 2 and paths[0].exists()


@pytest.mark.parametrize('mutation',['node-symbol','edge-symbol','quote-id','hash','empty','over-limit','condition','invented-hash'])
def test_invalid_model_draft_preserves_existing_outputs(tmp_cfg, automatic, mutation):
    section, model, save, agent=automatic
    path=Generator(tmp_cfg,model,agent).run()[0]
    site=export_site(tmp_cfg)
    before=path.read_bytes(); manifest=(site/'site-manifest.json').read_bytes()
    record=model.evidence['device/shutdown/stop']
    record['text']+=' // new source'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    # Authored prose pins also need explicit source review for this fixture.
    section['design_topics'][0]['sources'][0]['sha256']=record['sha256']
    record['selector']=copy.deepcopy(section['design_topics'][0]['sources'][0])
    if mutation=='node-symbol': agent.draft['nodes'][0]['symbol']='invented'
    if mutation=='edge-symbol':
        record['text']+='\n\nAnotherOnlySymbol'
        record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
        section['design_topics'][0]['sources'][0]['sha256']=record['sha256']
        record['selector']=copy.deepcopy(section['design_topics'][0]['sources'][0])
        agent.draft['nodes'][0].update(symbol='AnotherOnlySymbol',quote_ids=['stop:1'])
    if mutation=='quote-id': agent.draft['edges'][0]['quote_ids']=['invented:99']
    if mutation=='hash': record['sha256']='0'*64
    if mutation=='empty': agent.draft['nodes']=[]
    if mutation=='over-limit': agent.draft['nodes']*=3
    if mutation=='condition': agent.draft['edges'][0]['condition_ref']='invented:false'
    if mutation=='invented-hash': agent.draft['nodes'][0]['sha256']='0'*64
    save()
    with pytest.raises(ValueError): Generator(tmp_cfg,model,agent).run()
    assert path.read_bytes()==before
    with pytest.raises((ValueError,RuntimeError)): export_site(tmp_cfg)
    assert (site/'site-manifest.json').read_bytes()==manifest


def test_changed_source_regenerates_and_tampered_draft_is_rejected(tmp_cfg, automatic):
    section,model,save,agent=automatic
    path=Generator(tmp_cfg,model,agent).run()[0]
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() { cancelPending(); notifyStopped(); }'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    section['design_topics'][0]['sources'][0]['sha256']=record['sha256']
    record['selector']=copy.deepcopy(section['design_topics'][0]['sources'][0])
    save()
    Generator(tmp_cfg,model,agent).run()
    assert len(agent.calls)==2
    text=path.read_text(encoding='utf-8')
    assert 'notifyStopped' in text
    meta,body=_split(text)
    meta['generated_visuals']['records']['stop-flow']['graph']['edges'][0]['label']='tampered'
    changed='---\n'+yaml.safe_dump(meta,allow_unicode=True)+'---\n'+body
    with pytest.raises(ValueError,match='differs'):
        from_manuscript(tmp_cfg,model,section,changed)


def test_visual_transport_failure_does_not_replace_any_selected_page(tmp_cfg, automatic):
    _,model,_,agent=automatic
    path=Generator(tmp_cfg,model,agent).run()[0]
    original=path.read_bytes()
    path.write_text(path.read_text(encoding='utf-8')+'\nchanged body',encoding='utf-8')
    changed=path.read_bytes()
    from sdd.llm import AgentError
    class Offline:
        def chat(self,*a,**k): raise AgentError('model offline')
    with pytest.raises(AgentError): Generator(tmp_cfg,model,Offline()).run()
    assert path.read_bytes()==changed and changed!=original


def test_condition_ids_copy_nested_guards_and_never_invent_negation():
    from sdd.generated_visuals import conditions, schema
    passages={'code:0':('code','if (ready() && matches("(")) { run(); }\nif (ret >= 0) done();')}
    assert conditions(passages)==['', 'ready() && matches("(")', 'ret >= 0']
    choices=schema(passages,4)['properties']['edges']['items']['properties']['condition_ref']['enum']
    assert choices==['always','c0:true','c0:false','c1:true','c1:false']
    assert all('ret < 0' not in choice for choice in choices)


def test_switching_model_connection_regenerates_draft(tmp_cfg, automatic):
    _,model,_,agent=automatic
    Generator(tmp_cfg,model,agent).run()
    tmp_cfg.agent.model='internal-model'
    Generator(tmp_cfg,model,agent).run()
    assert len(agent.calls)==2


def test_dry_run_and_unauthored_plan_cannot_fake_a_draft(tmp_cfg, automatic):
    _,model,_,agent=automatic
    tmp_cfg.agent.kind='dry-run'
    with pytest.raises(ValueError,match='actual model'):
        Generator(tmp_cfg,model,agent).run()
    assert not agent.calls
    assert not (tmp_cfg.sdd_dir/'device.md').exists()


def test_source_question_view_cannot_bypass_required_answers(tmp_cfg, automatic):
    section, model, save, agent = automatic
    section['design_topics'][0]['narration'] = 'facts'
    save()
    with pytest.raises(ValueError, match='cannot replace required design answers'):
        Generator(tmp_cfg, model, agent).run()
    assert not agent.calls


def test_source_question_view_places_actual_model_graph_without_claiming_answer(tmp_cfg, automatic):
    section, model, save, agent = automatic
    section.pop('design_requirements')
    topic = section['design_topics'][0]
    topic.pop('statements')
    topic['narration'] = 'facts'
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8')
    assert topic['question'] in text and 'LLM 그림 초안' in text
    assert len(agent.calls) == 1
    assert _split(text)[0]['generation_method'] == 'source-question'


def test_compatible_gateway_uses_same_checks_without_ollama_schema(tmp_cfg, automatic):
    _, model, _, agent = automatic
    tmp_cfg.agent.kind = 'openai-compatible'
    Generator(tmp_cfg, model, agent).run()
    assert 'response_schema' not in agent.calls[0][2]


def test_diagram_labels_must_cover_question_contract(tmp_cfg, automatic):
    _, model, _, agent = automatic
    file = tmp_cfg.root / 'visuals.yaml'
    data = yaml.safe_load(file.read_text(encoding='utf-8'))
    plan = data['sections']['device'][0]
    plan['answer_contract'] = {'basis': 'description', 'required_terms': [['취소'], ['반환']]}
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='필수 용어 누락: 반환'):
        Generator(tmp_cfg, model, agent).run()
    agent.draft['edges'][0]['label'] = '대기 요청 취소 후 반환'
    Generator(tmp_cfg, model, agent).run()


def test_per_question_limit_cannot_exceed_project_ceiling(tmp_cfg, automatic):
    _, model, _, agent = automatic
    file = tmp_cfg.root / 'visuals.yaml'
    data = yaml.safe_load(file.read_text(encoding='utf-8'))
    data['sections']['device'][0]['max_nodes'] = 5
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='within visuals.max_nodes'):
        Generator(tmp_cfg, model, agent).run()
    assert not agent.calls


def test_english_label_coverage_is_checked_separately(tmp_cfg, automatic):
    _, model, _, agent = automatic
    file = tmp_cfg.root / 'visuals.yaml'
    data = yaml.safe_load(file.read_text(encoding='utf-8'))
    data['sections']['device'][0]['answer_contract_en'] = {'basis': 'description', 'required_terms': [['may']]}
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='stop-flow/en'):
        Generator(tmp_cfg, model, agent).run()
    agent.draft['edges'][0]['label_en'] = 'Pending requests may be cancelled'
    Generator(tmp_cfg, model, agent).run()


def test_full_required_symbol_set_uses_bound_object_supported_by_ollama():
    from sdd.generated_visuals import schema, expand_draft
    nodes = schema({'code:0': ('code', 'stop(); cancel();')}, 2, ['stop', 'cancel'])['properties']['nodes']
    assert nodes['type'] == 'object' and nodes['required'] == ['n0', 'n1']
    value = dict(label='Stop', label_en='Stop', shape='box', quote_ids=['code:0'])
    expanded = expand_draft({'required_symbols': ['stop', 'cancel']}, {'nodes': {'n0': value, 'n1': value}, 'edges': []}, 2)
    assert [n['symbol'] for n in expanded['nodes']] == ['stop', 'cancel']
    with pytest.raises(ValueError, match='missing or unknown'):
        expand_draft({'required_symbols': ['stop', 'cancel']}, {'nodes': {'n0': value}}, 2)


def test_status_passages_remain_verbatim_and_keep_caller_duties():
    from sdd.generated_visuals import visual_passages
    text = '\\fn Config::validate()\n * Returns status.\n * \\retval Config::Invalid Cannot adjust.\n * \\retval Config::Adjusted Parameters may change.\n * Caller shall check carefully.\n * \\retval Config::Valid Already valid.'
    _, passages = visual_passages({'validate': text})
    assert len(passages) == 4
    assert all(quote in text for _, quote in passages.values())
    assert 'Caller shall check carefully.' in passages['validate:2'][1]


def test_exact_source_guard_labels_allowed_but_old_guard_rejected(tmp_cfg, automatic):
    section, model, save, agent = automatic
    record = model.evidence['device/shutdown/stop']
    def change(expression):
        record['text'] = 'void Device::stop() { cancelPending(); }\nif (' + expression + ') { stop(); cancelPending(); }'
        record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
        section['design_topics'][0]['sources'][0]['sha256'] = record['sha256']
        record['selector'] = copy.deepcopy(section['design_topics'][0]['sources'][0])
        save()
    change('ret == 0')
    agent.draft['edges'][0].update(label='취소 ret == 0', label_en='Cancel ret == 0', condition_ref='c0:true')
    Generator(tmp_cfg, model, agent).run()
    change('ret >= 0')
    with pytest.raises(ValueError, match='differs from cited source guards'):
        Generator(tmp_cfg, model, agent).run()


def test_long_bilingual_labels_wrap_without_losing_text_or_escaping():
    import html
    from sdd.visuals import wrap_label
    from sdd.site_localization import english_diagram
    ko = '호출자는 변경되었을 수 있는 스트림 구성을 주의하여 확인해야 합니다. <source> & 조건'
    en = 'The caller must carefully check stream configurations that may have changed. <source> & guard'
    left, right = wrap_label(ko), wrap_label(en)
    assert '<br/>' in left and '<br/>' in right
    assert html.unescape(left.replace('<br/>', '')) == ko
    assert html.unescape(right.replace('<br/>', '')) == en
    assert '<source>' not in left and '<source>' not in right
    source = 'flowchart TB\n%% sdd:translations ' + json.dumps({left: right}) + '\n v_n0["' + left + '"]'
    assert 'v_n0["' + right + '"]' in english_diagram(source)


def test_label_schema_matches_single_line_validator_for_nodes_and_edges():
    import re
    from sdd.generated_visuals import schema
    from sdd.visuals import _text
    result = schema({'source:0': ('source', 'stop(); cancel();')}, 2, ['stop', 'cancel'])
    for properties in [result['properties']['nodes']['properties']['n0']['properties'],
                       result['properties']['edges']['items']['properties']]:
        for field in ('label', 'label_en'):
            rule = properties[field]
            assert re.fullmatch(rule['pattern'], '상태 확인 / check state')
            assert _text('상태 확인 / check state', field)
            for value in ('', 'Adjusted\nCheck', 'Adjusted\rCheck'):
                assert not re.fullmatch(rule['pattern'], value)
                with pytest.raises(ValueError, match='single line'):
                    _text(value, field)


def test_visual_source_selection_excludes_unrelated_prose_evidence(tmp_cfg, automatic):
    from sdd.generated_visuals import inputs, plans
    section, model, _, _ = automatic
    topic = section['design_topics'][0]
    extra = copy.deepcopy(topic['sources'][0]); extra['id'] = 'other'
    topic['sources'].append(extra)
    record = copy.deepcopy(model.evidence['device/shutdown/stop'])
    record['text'] = 'unrelated();'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    extra['sha256'] = record['sha256']; record['selector'] = copy.deepcopy(extra)
    model.evidence['device/shutdown/other'] = record
    plan = plans(tmp_cfg, section)[0]
    plan['sources'] = ['stop']
    _, records, passages, _, request = inputs(tmp_cfg, model, section, plan)
    assert set(records) == {'stop'}
    assert all(source == 'stop' for source, _ in passages.values())
    assert 'unrelated' not in json.dumps(request)
    for invalid in ([], ['missing'], ['stop', 'stop'], 'stop', [None]):
        plan['sources'] = invalid
        with pytest.raises(ValueError, match='Visual sources'):
            inputs(tmp_cfg, model, section, plan)


def test_cli_executable_relocation_keeps_identities_while_wrapper_arguments_change_them(tmp_cfg, automatic):
    from sdd.generated_visuals import definitions, inputs
    section, model, save, _ = automatic
    tmp_cfg.agent.kind, tmp_cfg.agent.runner, tmp_cfg.agent.model = 'cli', 'codex', 'test-model'
    plan = next(p for p in definitions(tmp_cfg, section) if p.get('generation') == 'llm')

    def identities():
        return (inputs(tmp_cfg, model, section, plan)[0],)

    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\0ab0e7a8\codex.EXE']
    before = identities()
    # An app update moves the executable into another hashed folder.
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\22cfb1d3\codex.exe']
    assert identities() == before
    # Wrapper arguments still change what is executed.
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\22cfb1d3\codex.exe', '--profile', 'other']
    changed = identities()
    assert all(new != old for new, old in zip(changed, before))


@pytest.mark.parametrize('change', [None, 'source', 'args', 'pin'])
def test_exact_legacy_cli_visual_proof_is_verified_without_rewriting_its_history(tmp_cfg, automatic, change):
    from sdd.generated_visuals import generate, resolve
    section, model, _, agent = automatic
    tmp_cfg.agent.kind, tmp_cfg.agent.runner, tmp_cfg.agent.model = 'cli', 'codex', 'test-model'
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\0ab0e7a8\codex.EXE']
    artifact = generate(tmp_cfg, model, section, agent)
    # Frozen producer fingerprint from before executable identity normalization.
    legacy = '23cef34a22077e7a7c1ef0e646d0d7232cd3c6bbda4591effbcbc923b58cebfb'
    artifact['records']['stop-flow']['input_fingerprint'] = legacy
    original = copy.deepcopy(artifact)
    if change == 'source':
        record = model.evidence['device/shutdown/stop']
        record['text'] += '\n// changed source'
        record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    elif change == 'args':
        tmp_cfg.agent.args = ['--profile', 'other']
    elif change == 'pin':
        artifact['records']['stop-flow']['input_fingerprint'] = '0'*64
    if change:
        with pytest.raises(ValueError):
            resolve(tmp_cfg, model, section, artifact)
    else:
        assert resolve(tmp_cfg, model, section, artifact)
        assert artifact == original
        assert len(agent.calls) == 1
