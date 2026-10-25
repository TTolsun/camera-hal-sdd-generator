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
