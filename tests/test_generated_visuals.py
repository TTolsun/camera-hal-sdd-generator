import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.generated_visuals import from_manuscript
from sdd.carryover import carry_forward
from sdd.export_html import _split
from test_design_contracts import contract


def test_native_stage_places_figure_beside_its_own_explanation(tmp_cfg, automatic):
    from sdd.explanation import STAGES
    from sdd.generated_visuals import inputs, materialize, plans
    from sdd.visuals import render_values, place
    section,model,_,agent=automatic
    topic=section['design_topics'][0]
    topic.pop('statements')
    topic['parts']=[dict(id=s,question=s,sources=['stop']) for s in STAGES]
    topic['explanation']=[dict(id=s,title=s.title(),parts=[s]) for s in STAGES]
    base=plans(tmp_cfg,section)[0]
    staged={**base,'stage':'principle'}
    assert inputs(tmp_cfg,model,section,base)[0]!=inputs(tmp_cfg,model,section,staged)[0]
    graph=materialize(tmp_cfg,model,section,staged,agent.draft,'synthetic-stage-fixture')
    body='## '+topic['title']+'\n\n'+'\n\n'.join('### '+s.title()+'\n\n'+s+' explanation.' for s in STAGES)+'\n'
    result=place(body,render_values(tmp_cfg,model,section,[graph]),section)
    marker='<!-- sdd:visual:stop-flow -->'
    assert result.index('### Principle')<result.index(marker)<result.index('### Normal')
    assert marker not in result.split('### Principle')[0]
    artifact=dict(schema=1,records={'stop-flow':dict(input_fingerprint=inputs(tmp_cfg,model,section,staged)[0],
                  draft=agent.draft,graph=graph,producer='synthetic-stage-fixture',generation_commit='a'*40)})
    def manuscript(text):
        artifact['body_sha256']=hashlib.sha256(text.strip().encode()).hexdigest()
        return '---\ngenerated_visuals: '+json.dumps(artifact,ensure_ascii=False)+'\n---\n'+text
    config=tmp_cfg.root/'visuals.yaml'
    config.write_text(yaml.safe_dump(dict(schema=1,sections={'device':[staged]}),allow_unicode=True),encoding='utf-8')
    from_manuscript(tmp_cfg,model,section,manuscript(result))
    block=render_values(tmp_cfg,model,section,[graph])[0][1]
    misplaced=result.replace(block,'').replace('problem explanation.','problem explanation.\n\n'+block)
    with pytest.raises(ValueError,match='outside its declared explanation stage'):
        from_manuscript(tmp_cfg,model,section,manuscript(misplaced))
    detached=result.replace(block,marker).replace('normal explanation.','normal explanation.\n\n'+block[len(marker):])
    with pytest.raises(ValueError,match='stage block'):
        from_manuscript(tmp_cfg,model,section,manuscript(detached))
    changed=result.replace('cancelPending','fabricatedCall')
    with pytest.raises(ValueError,match='stage block'):
        from_manuscript(tmp_cfg,model,section,manuscript(changed))
    assert not agent.calls


def test_graph_refresh_rejects_declarative_addition_in_another_stage(tmp_cfg,automatic):
    from sdd.explanation import STAGES
    from sdd.generated_visuals import materialize,plans
    from sdd.visuals import render_values,place
    from sdd.visual_refresh import _reassemble
    section,model,_,agent=automatic
    topic=section['design_topics'][0]
    topic['explanation']=[dict(id=s,title=s.title(),parts=[s]) for s in STAGES]
    graph=materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],agent.draft,'synthetic-native-fixture')
    old=render_values(tmp_cfg,model,section,[graph])
    body='## '+topic['title']+'\n\n'+'\n\n'.join('### '+s.title()+'\n\n'+s+' explanation.' for s in STAGES)+'\n'
    body=place(body,old,section)
    addition={**graph,'id':'declarative-normal','stage':'normal'}
    addition.pop('producer')
    rendered=render_values(tmp_cfg,model,section,[graph,addition])
    with pytest.raises(ValueError,match='without an existing anchor requires normal generation'):
        _reassemble(body,body,lambda offset:offset,rendered,section)


@pytest.mark.parametrize('stage',['missing',None,[]])
def test_native_stage_rejects_unknown_owner_before_model_call(tmp_cfg,automatic,stage):
    from sdd.generated_visuals import inputs,plans
    section,model,_,agent=automatic
    with pytest.raises(ValueError,match='stage'):
        inputs(tmp_cfg,model,section,{**plans(tmp_cfg,section)[0],'stage':stage})
    assert not agent.calls


def test_versioned_symbol_policies_recognize_exact_legacy_input_pins(tmp_cfg, automatic, monkeypatch):
    import sdd.generated_visuals as visuals
    monkeypatch.setattr(visuals, 'POLICY', 'Synthetic schema compatibility policy.')
    (tmp_cfg.style_dir / 'README.md').write_text('', encoding='utf-8')
    tmp_cfg.agent.model = 'synthetic-schema-model'
    tmp_cfg.agent.base_url = 'http://synthetic.invalid'
    section, model, _, _ = automatic
    base = visuals.plans(tmp_cfg, section)[0]
    values = {
        'ordinary': visuals.inputs(tmp_cfg, model, section, base)[0],
        'partial': visuals.inputs(tmp_cfg, model, section, {**base, 'required_symbols': ['stop']})[0],
        'fixed': visuals.inputs(tmp_cfg, model, section, {**base, 'required_symbols': ['stop', 'cancelPending'], 'max_nodes': 2})[0],
    }
    # Old hashes remain reproducible for strict current-policy revalidation.
    old_ordinary = '5188100aa2aa3118bb257989df3307773130c50d2200f802bd07fed92eb391c2'
    old_fixed = 'd593a081a484e6beb58704d795d25edb80a46347b13de5e0b6320052287ceb1f'
    assert values['ordinary'] != old_ordinary
    assert values['fixed'] != old_fixed
    assert visuals.inputs(tmp_cfg, model, section, base, _legacy_citation_binding=True)[0] == old_ordinary
    assert visuals.inputs(tmp_cfg, model, section, {**base, 'required_symbols':['stop','cancelPending'], 'max_nodes':2}, _legacy_citation_binding=True)[0] == old_fixed
    assert values['partial'] != '855ea682c48eb8d19cb75af09e722c21375a705e916d1bd3fb8dce76120517c6'
    assert visuals.inputs(tmp_cfg, model, section, {**base, 'required_symbols':['stop']}, _legacy_citation_binding=True)[0] != '855ea682c48eb8d19cb75af09e722c21375a705e916d1bd3fb8dce76120517c6'


def test_required_symbol_allows_additional_cited_nodes_but_keeps_coverage(tmp_cfg, automatic):
    from sdd.cli_schema import validate_original
    from sdd.generated_visuals import inputs, materialize, plans, schema
    section, model, _, agent = automatic
    plan = {**plans(tmp_cfg, section)[0], 'required_symbols': ['stop']}
    _, _, passages, _, request = inputs(tmp_cfg, model, section, plan)
    rules = schema(passages, 4, plan['required_symbols'])
    assert rules['properties']['nodes']['items']['properties']['symbol']['enum'] == request['allowed_symbols']
    validate_original(json.dumps(agent.draft), rules)
    result = materialize(tmp_cfg, model, section, plan, agent.draft, 'synthetic-unit-fixture')
    assert [node['id'] for node in result['nodes']] == ['stop', 'cancel']
    missing = copy.deepcopy(agent.draft)
    missing['nodes'][0]['symbol'] = 'cancelPending'
    validate_original(json.dumps(missing), rules)
    with pytest.raises(ValueError, match='missing required question symbols: stop'):
        materialize(tmp_cfg, model, section, plan, missing, 'synthetic-unit-fixture')
    unknown = copy.deepcopy(agent.draft)
    unknown['nodes'][1]['symbol'] = 'notInSelectedSource'
    with pytest.raises(ValueError, match='output schema'):
        validate_original(json.dumps(unknown), rules)
    with pytest.raises(ValueError, match='symbol absent'):
        materialize(tmp_cfg, model, section, plan, unknown, 'synthetic-unit-fixture')
    assert not agent.calls


def test_partial_required_symbols_validate_schema_and_preserve_outputs_on_failure(tmp_cfg, automatic):
    from sdd.cli_schema import validate_original
    section, model, _, agent = automatic
    config = tmp_cfg.root/'visuals.yaml'
    data = yaml.safe_load(config.read_bytes())
    data['sections']['device'][0]['required_symbols'] = ['stop']
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    original_chat = agent.chat
    def schema_checked_chat(*args, **kwargs):
        raw = original_chat(*args, **kwargs)
        validate_original(raw, kwargs['response_schema'])
        return raw
    agent.chat = schema_checked_chat
    path = Generator(tmp_cfg, model, agent).run()[0]
    site = export_site(tmp_cfg)
    outputs = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*') if p.is_file()}
    initial_calls = len(agent.calls)
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == initial_calls
    original = path.read_bytes()
    data['sections']['device'][0]['prompt'] = 'Reconsider the same source-backed question.'
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    agent.draft['nodes'][0]['symbol'] = 'cancelPending'
    with pytest.raises(ValueError, match='missing required question symbols: stop'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='regenerate before publishing'):
        export_site(tmp_cfg)
    assert {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob('*') if p.is_file()} == outputs


@pytest.mark.parametrize('symbol,longer', [('run','Device::runner')] + [('Device::run',longer) for longer in [
    'Device::runner', 'Device::run::other', 'Device::run ::other',
    'Device::run /* scope */ :: /* member */ other', 'Device::run // scope\n ::other',
    'Device::run\\\n::other',
]] + [('Device::run', 'Device /* a */ (); other /* b */ ::run')])
def test_optional_source_symbols_cannot_bind_to_longer_names(tmp_cfg, automatic, symbol, longer):
    from sdd.cli_schema import validate_original
    from sdd.generated_visuals import inputs, materialize, plans, schema
    section, model, _, agent = automatic
    text = f'void Device::stop() {{ {longer}(); }}\n\nvoid Device::run() {{ stop(); }}'
    source = section['design_topics'][0]['sources'][0]
    source.update(end='void Device::run() { stop(); }', sha256=hashlib.sha256(text.encode()).hexdigest())
    record = model.evidence['device/shutdown/stop']
    record.update(text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    plan = {**plans(tmp_cfg, section)[0], 'required_symbols': ['stop']}
    _, _, passages, _, _ = inputs(tmp_cfg, model, section, plan)
    draft = copy.deepcopy(agent.draft)
    draft['nodes'][1].update(id='run', symbol=symbol, label='run 호출', label_en='Call run.', quote_ids=['stop:1'])
    draft['edges'][0].update(**{'from': 'run', 'to': 'stop'}, quote_ids=['stop:1'])
    rules = schema(passages, 4, ['stop'])
    validate_original(json.dumps(draft), rules)
    materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')
    bad_node = copy.deepcopy(draft)
    bad_node['nodes'][1]['quote_ids'] = ['stop:0']
    validate_original(json.dumps(bad_node), rules)
    with pytest.raises(ValueError, match='symbol absent'):
        materialize(tmp_cfg, model, section, plan, bad_node, 'synthetic-unit-fixture')
    bad_edge = copy.deepcopy(draft)
    bad_edge['edges'][0]['quote_ids'] = ['stop:0']
    validate_original(json.dumps(bad_edge), rules)
    with pytest.raises(ValueError, match='both endpoint symbols'):
        materialize(tmp_cfg, model, section, plan, bad_edge, 'synthetic-unit-fixture')
    fixed_rules = schema(passages, 2, ['stop', symbol])
    fixed = {
        'nodes': {
            'n0': {k: v for k, v in draft['nodes'][0].items() if k not in ('id', 'symbol')},
            'n1': {k: v for k, v in draft['nodes'][1].items() if k not in ('id', 'symbol')},
        },
        'edges': [{**draft['edges'][0], 'from': 'n1', 'to': 'n0'}],
    }
    validate_original(json.dumps(fixed), fixed_rules)
    fixed['nodes']['n1']['quote_ids'] = ['stop:0']
    validate_original(json.dumps(fixed), fixed_rules)
    with pytest.raises(ValueError, match='symbol absent'):
        materialize(tmp_cfg, model, section, {**plan,'required_symbols':['stop',symbol],'max_nodes':2}, fixed, 'synthetic-unit-fixture')
    assert not agent.calls


@pytest.mark.parametrize('qualified', ['ns::Device::run', 'ns::Device /* scope */ :: run', 'ns::Device\\\n::run'])
def test_qualified_symbol_suffix_is_citable_in_native_and_fixed_shapes(tmp_cfg, automatic, qualified):
    from sdd.cli_schema import validate_original
    from sdd.generated_visuals import inputs, materialize, plans, schema
    section, model, _, agent = automatic
    text = f'void Device::stop() {{ {qualified}(); }}\n\nvoid finish() {{ stop(); }}'
    source = section['design_topics'][0]['sources'][0]
    source.update(end='void finish() { stop(); }', sha256=hashlib.sha256(text.encode()).hexdigest())
    model.evidence['device/shutdown/stop'].update(
        text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    plan = {**plans(tmp_cfg, section)[0], 'required_symbols': ['stop']}
    _, _, passages, _, request = inputs(tmp_cfg, model, section, plan)
    assert 'Device::run' in request['allowed_symbols']
    assert 'Device' in request['allowed_symbols']
    inputs(tmp_cfg, model, section, {**plan, 'required_symbols':['Device','stop'], 'max_nodes':2})
    inputs(tmp_cfg, model, section, {**plan, 'required_symbols':['stop','Device::run']})
    draft = copy.deepcopy(agent.draft)
    draft['nodes'][1].update(id='run', symbol='Device::run', label='ns::Device::run 호출',
        label_en='Call ns::Device::run.', quote_ids=['stop:0'])
    draft['edges'][0].update(**{'from':'stop','to':'run'}, label='한정 이름으로 호출합니다.',
        label_en='Call the qualified function.', quote_ids=['stop:0'])
    validate_original(json.dumps(draft), schema(passages, 4, ['stop']))
    materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')
    fixed_plan = {**plan, 'required_symbols':['stop','Device::run'], 'max_nodes':2}
    fixed = {
        'nodes': {f'n{i}': {k:v for k,v in node.items() if k not in ('id','symbol')}
                  for i,node in enumerate(draft['nodes'])},
        'edges': [{**draft['edges'][0], 'from':'n0', 'to':'n1'}],
    }
    validate_original(json.dumps(fixed), schema(passages, 2, fixed_plan['required_symbols']))
    materialize(tmp_cfg, model, section, fixed_plan, fixed, 'synthetic-unit-fixture')
    fixed['nodes']['n1']['quote_ids'].append('stop:1')
    validate_original(json.dumps(fixed), schema(passages, 2, fixed_plan['required_symbols']))
    materialize(tmp_cfg, model, section, fixed_plan, fixed, 'synthetic-unit-fixture')
    assert not agent.calls


def test_symbols_cannot_be_assembled_across_cited_passages(tmp_cfg, automatic):
    from sdd.cli_schema import validate_original
    from sdd.generated_visuals import inputs, materialize, plans, schema
    section, model, _, agent = automatic
    text = 'some_long_name Device\n\n::run stop(); return;\n\nvoid Device::run() { stop(); }'
    source = section['design_topics'][0]['sources'][0]
    source.update(end='void Device::run() { stop(); }', sha256=hashlib.sha256(text.encode()).hexdigest())
    model.evidence['device/shutdown/stop'].update(
        text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    plan = {**plans(tmp_cfg, section)[0], 'required_symbols':['stop']}
    _, _, passages, _, _ = inputs(tmp_cfg, model, section, plan)
    draft = copy.deepcopy(agent.draft)
    draft['nodes'][0]['quote_ids'] = ['stop:2']
    draft['nodes'][1].update(id='run', symbol='Device::run', label='run 호출',
        label_en='Call run.', quote_ids=['stop:2'])
    draft['edges'][0].update(**{'from':'stop', 'to':'run'}, quote_ids=['stop:2'])
    materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')
    for kind, message in [('nodes','symbol absent'), ('edges','both endpoint symbols')]:
        invalid = copy.deepcopy(draft)
        invalid[kind][1 if kind == 'nodes' else 0]['quote_ids'] = ['stop:0','stop:1']
        validate_original(json.dumps(invalid), schema(passages, 4, ['stop']))
        with pytest.raises(ValueError, match=message):
            materialize(tmp_cfg, model, section, plan, invalid, 'synthetic-unit-fixture')
    fixed = {
        'nodes': {f'n{i}': {k:v for k,v in node.items() if k not in ('id','symbol')}
                  for i,node in enumerate(draft['nodes'])},
        'edges': [{**draft['edges'][0], 'from':'n0', 'to':'n1'}],
    }
    rules = schema(passages, 2, ['stop','Device::run'])
    validate_original(json.dumps(fixed), rules)
    fixed['nodes']['n1']['quote_ids'] = ['stop:0','stop:1']
    validate_original(json.dumps(fixed), rules)
    with pytest.raises(ValueError, match='symbol absent'):
        materialize(tmp_cfg, model, section, {**plan,'required_symbols':['stop','Device::run'],'max_nodes':2}, fixed, 'synthetic-unit-fixture')
    assert not agent.calls


def _synthetic_legacy_visual_document(record):
    """Unit fixture only; never a native call or publication review record."""
    body = 'Synthetic legacy fixture body.'
    artifact = {'schema':1, 'records':{'stop-flow':record},
                'body_sha256':hashlib.sha256(body.encode()).hexdigest()}
    return '---\n' + yaml.safe_dump({'generated_visuals':artifact}, allow_unicode=True) + '---\n' + body


@pytest.mark.parametrize('fixed,qualifier', [(False,False),(True,False),(True,True)])
def test_legacy_binding_is_revalidated_without_repinning_or_inference(tmp_cfg, automatic, fixed, qualifier):
    from sdd.generated_visuals import CITATION_BINDING_POLICY, generate, inputs, materialize, plans, resolve
    section, model, _, agent = automatic
    config = tmp_cfg.root/'visuals.yaml'
    data = yaml.safe_load(config.read_bytes())
    if qualifier:
        text = 'void stop() { Device::run(); }'
        source = section['design_topics'][0]['sources'][0]
        source.update(end=text, sha256=hashlib.sha256(text.encode()).hexdigest())
        model.evidence['device/shutdown/stop'].update(
            text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    if fixed:
        data['sections']['device'][0].update(required_symbols=['stop','Device' if qualifier else 'cancelPending'], max_nodes=2)
        config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    plan = plans(tmp_cfg, section)[0]
    draft = copy.deepcopy(agent.draft)
    if fixed:
        draft = {'nodes':{f'n{i}':{k:v for k,v in node.items() if k not in ('id','symbol')}
                          for i,node in enumerate(draft['nodes'])},
                 'edges':[{**draft['edges'][0], 'from':'n0', 'to':'n1'}]}
    original_pin = inputs(tmp_cfg, model, section, plan, _legacy_citation_binding=True)[0]
    assert original_pin != inputs(tmp_cfg, model, section, plan)[0]
    record = {'input_fingerprint':original_pin, 'draft':draft,
              'graph':materialize(tmp_cfg, model, section, plan, draft, 'synthetic-legacy-fixture'),
              'producer':'synthetic-legacy-fixture', 'generation_commit':'a'*40,
              'human_review':'pending', 'reused':False}
    previous = _synthetic_legacy_visual_document(record)
    with pytest.raises(ValueError, match='recorded citation revalidation'):
        resolve(tmp_cfg, model, section, {'schema':1, 'records':{'stop-flow':record}})
    spoofed = {**record, 'citation_binding_policy':CITATION_BINDING_POLICY}
    with pytest.raises(ValueError, match='recorded citation revalidation'):
        resolve(tmp_cfg, model, section, {'schema':1, 'records':{'stop-flow':spoofed}})
    class NoInference:
        def chat(self, *args, **kwargs):pytest.fail('Valid legacy binding should be revalidated without inference')
    artifact = generate(tmp_cfg, model, section, NoInference(), previous)
    reused = artifact['records']['stop-flow']
    for key in ('input_fingerprint','draft','graph','producer','generation_commit','human_review'):
        assert reused[key] == record[key]
    assert reused['citation_binding_revalidation'] == {
        'policy':CITATION_BINDING_POLICY, 'original_input_fingerprint':original_pin, 'new_inference':False}
    assert reused['reused'] is True
    assert resolve(tmp_cfg, model, section, artifact) == [record['graph']]
    assert previous == _synthetic_legacy_visual_document(record)
    tampered = copy.deepcopy(artifact)
    tampered['records']['stop-flow']['citation_binding_revalidation']['original_input_fingerprint'] = '0'*64
    with pytest.raises(ValueError, match='recorded citation revalidation'):
        resolve(tmp_cfg, model, section, tampered)
    for value in [0, 1, 'false', None]:
        tampered = copy.deepcopy(artifact)
        tampered['records']['stop-flow']['citation_binding_revalidation']['new_inference'] = value
        with pytest.raises(ValueError, match='recorded citation revalidation'):
            resolve(tmp_cfg, model, section, tampered)
    tmp_cfg.agent.model += '-changed'
    with pytest.raises(ValueError, match='changed; regenerate'):
        resolve(tmp_cfg, model, section, artifact)


def test_incompatible_legacy_binding_is_stale_and_uses_selected_agent(tmp_cfg, automatic, monkeypatch):
    import sdd.generated_visuals as visuals
    from sdd.llm import AgentError
    section, model, _, agent = automatic
    text = 'void Device::stop() { Device::runner(); }\n\nvoid Device::run() { stop(); }'
    source = section['design_topics'][0]['sources'][0]
    source.update(end='void Device::run() { stop(); }', sha256=hashlib.sha256(text.encode()).hexdigest())
    model.evidence['device/shutdown/stop'].update(
        text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    plan = visuals.plans(tmp_cfg, section)[0]
    correct = copy.deepcopy(agent.draft)
    correct['nodes'][1].update(id='run', symbol='Device::run', label='run 호출', label_en='Call run.', quote_ids=['stop:1'])
    correct['edges'][0].update(**{'from':'run','to':'stop'}, quote_ids=['stop:1'])
    bad = copy.deepcopy(correct)
    bad['nodes'][1]['quote_ids'] = ['stop:0']
    bad['edges'][0]['quote_ids'] = ['stop:0']
    with monkeypatch.context() as legacy:
        legacy.setattr(visuals, 'cites_symbol', lambda symbol, quote: symbol in quote)
        graph = visuals.materialize(tmp_cfg, model, section, plan, bad, 'synthetic-legacy-fixture')
    record = {'input_fingerprint':visuals.inputs(tmp_cfg, model, section, plan, _legacy_citation_binding=True)[0],
              'draft':bad, 'graph':graph, 'producer':'synthetic-legacy-fixture', 'generation_commit':'a'*40}
    previous = _synthetic_legacy_visual_document(record)
    with pytest.raises(ValueError, match='citation binding is stale; regenerate'):
        visuals.resolve(tmp_cfg, model, section, {'schema':1, 'records':{'stop-flow':record}})
    class Unavailable:
        def chat(self, *args, **kwargs):raise AgentError('Selected runner unavailable')
    with pytest.raises(AgentError, match='Selected runner unavailable'):
        visuals.generate(tmp_cfg, model, section, Unavailable(), previous)
    agent.draft = correct
    fresh = visuals.generate(tmp_cfg, model, section, agent, previous)['records']['stop-flow']
    assert len(agent.calls) == 1
    assert fresh['input_fingerprint'] == visuals.inputs(tmp_cfg, model, section, plan)[0]
    assert fresh['input_fingerprint'] != record['input_fingerprint']
    assert fresh['citation_binding_policy'] == visuals.CITATION_BINDING_POLICY
    assert fresh['reused'] is False
    assert previous == _synthetic_legacy_visual_document(record)


def test_atomic_source_window_keeps_short_returns_and_repeated_fragments(tmp_cfg,automatic):
    from sdd.generated_visuals import inputs,materialize,plans,visual_passages
    from sdd.design_response import source_passages
    section,model,_,agent=automatic
    text='int Device::stop() {\n    cancelPending();\n\n    return 0;\n}'
    record=model.evidence['device/shutdown/stop']
    record.update(text=text,sha256=hashlib.sha256(text.encode()).hexdigest())
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    plan=plans(tmp_cfg,section)[0]
    ordinary=inputs(tmp_cfg,model,section,plan)
    assert visual_passages({'stop':text})==source_passages({'stop':text})
    assert not any('return 0;' in quote for _,quote in ordinary[2].values())
    atomic={**plan,'whole_sources':['stop']}
    full=inputs(tmp_cfg,model,section,atomic)
    assert full[0]!=ordinary[0]
    assert full[2]=={'stop:0':('stop',text)}
    draft=copy.deepcopy(agent.draft)
    draft['nodes'].append(dict(id='done',symbol='stop',label='0을 반환합니다.',
        label_en='It returns 0.',shape='box',quote_ids=['stop:0']))
    draft['edges'].append(dict(**{'from':'cancel','to':'done'},label='호출 뒤 반환합니다.',
        label_en='It returns after the call.',condition_ref='always',quote_ids=['stop:0']))
    graph=materialize(tmp_cfg,model,section,atomic,draft,'synthetic-unit-fixture')
    assert 'whole_sources' not in graph
    assert 'return 0;' in graph['nodes'][-1]['evidence'][0]['quote']
    assert not agent.calls
    repeated='int call() {\n    erase(iter);\n\n    if (failed) { erase(iter); return -1; }\n\n    erase(iter);\n\n    return 0;\n}'
    _,quotes=visual_passages({'call':repeated},whole_sources=['call'])
    assert quotes['call:0']==('call',repeated)
    assert repeated.count(quotes['call:0'][1])==1


@pytest.mark.parametrize('value',[True,None,'stop',['missing'],['stop','stop'],[None],{}])
def test_atomic_source_scope_rejects_invalid_or_unselected_windows(tmp_cfg,automatic,value):
    from sdd.generated_visuals import inputs,plans
    section,model,_,agent=automatic
    plan={**plans(tmp_cfg,section)[0],'whole_sources':value}
    with pytest.raises(ValueError,match='whole_sources'):
        inputs(tmp_cfg,model,section,plan)
    assert not agent.calls


def test_atomic_source_opt_in_regenerates_then_reuses_with_normal_export(tmp_cfg,automatic):
    section,model,save,agent=automatic
    path=Generator(tmp_cfg,model,agent).run()[0]
    initial_calls=len(agent.calls)
    config=tmp_cfg.root/'visuals.yaml'
    data=yaml.safe_load(config.read_text(encoding='utf-8'))
    data['sections']['device'][0]['whole_sources']=['stop']
    config.write_text(yaml.safe_dump(data,allow_unicode=True),encoding='utf-8')
    Generator(tmp_cfg,model,agent).run()
    assert len(agent.calls)==initial_calls+1
    Generator(tmp_cfg,model,agent).run()
    assert len(agent.calls)==initial_calls+1
    assert (export_site(tmp_cfg)/'device.html').is_file()
    generated=path.read_bytes()
    model.evidence['device/shutdown/stop']['sha256']='0'*64
    with pytest.raises(ValueError,match='hash|지문|근거|changed'):
        Generator(tmp_cfg,model,agent).run()
    assert path.read_bytes()==generated


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
    # Renamed figures keep their published anchors as explicit local routes.
    aliases = [r for r in sections[target].get('routes', []) if r.get('anchor') == anchor]
    if aliases:
        assert len(aliases) == 1
        assert aliases[0]['to'].startswith('#')
        anchor = aliases[0]['to'][1:]
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


def test_guard_branch_check_is_optional_and_preserves_source_conditions(tmp_cfg, automatic):
    from sdd.generated_visuals import inputs, materialize, plans
    section, model, save, agent = automatic
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { if (ready()) { cancelPending(); } else { keepPending(); } }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    section['design_topics'][0]['sources'][0]['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(section['design_topics'][0]['sources'][0])
    save()
    plan = plans(tmp_cfg, section)[0]
    draft = copy.deepcopy(agent.draft)
    draft['edges'][0]['condition_ref'] = 'c0:true'
    # Existing diagrams retain their prior interpretation unless opted in.
    legacy = materialize(tmp_cfg, model, section, plan, draft, 'test')
    assert 'ready() [true]' in legacy['edges'][0]['label']
    restricted = {**plan, 'require_guard_branches': True}
    with pytest.raises(ValueError, match='non-decision node stop'):
        materialize(tmp_cfg, model, section, restricted, draft, 'test')
    draft['nodes'][0]['shape'] = 'decision'
    with pytest.raises(ValueError, match='true and false outcomes'):
        materialize(tmp_cfg, model, section, restricted, draft, 'test')
    draft['nodes'].append(dict(id='keep', symbol='keepPending', label='대기 유지',
                               label_en='Keep pending', shape='box', quote_ids=['stop:0']))
    draft['edges'].append(dict(**{'from': 'stop', 'to': 'keep'}, label='대기',
                              label_en='Wait', condition_ref='c0:false', quote_ids=['stop:0']))
    graph = materialize(tmp_cfg, model, section, restricted, draft, 'test')
    assert 'require_guard_branches' not in graph
    assert 'ready() [true]' in graph['edges'][0]['label']
    assert 'ready() [false]' in graph['edges'][1]['label']
    for invalid in ['true', 1, None]:
        with pytest.raises(ValueError, match='require_guard_branches must be boolean'):
            inputs(tmp_cfg, model, section, {**plan, 'require_guard_branches': invalid})


def test_incomplete_guard_branch_preserves_prior_manuscript(tmp_cfg, automatic):
    section, model, save, agent = automatic
    path = Generator(tmp_cfg, model, agent).run()[0]
    previous = path.read_bytes()
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { if (ready()) { cancelPending(); } }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    section['design_topics'][0]['sources'][0]['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(section['design_topics'][0]['sources'][0])
    save()
    p = tmp_cfg.root/'visuals.yaml'
    data = yaml.safe_load(p.read_text(encoding='utf-8'))
    data['sections']['device'][0]['require_guard_branches'] = True
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    agent.draft['nodes'][0]['shape'] = 'decision'
    agent.draft['edges'][0]['condition_ref'] = 'c0:true'
    tmp_cfg.max_retries = 0
    with pytest.raises(ValueError, match='true and false outcomes'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == previous
def test_citation_failure_identifies_the_node_and_unknown_edge_endpoint(tmp_cfg, automatic):
    from sdd.generated_visuals import materialize, plans
    section, model, _, agent = automatic
    plan = plans(tmp_cfg, section)[0]
    bad = copy.deepcopy(agent.draft)
    bad['nodes'][1]['symbol'] = 'not_in_evidence'
    with pytest.raises(ValueError, match='symbol absent') as error:
        materialize(tmp_cfg, model, section, plan, bad, 'synthetic-diagnostic-fixture')
    assert all(value in str(error.value) for value in ('cancel', 'not_in_evidence', 'stop:0'))
    bad = copy.deepcopy(agent.draft)
    bad['edges'][0]['to'] = 'unknown_destination'
    with pytest.raises(ValueError, match='both endpoint symbols') as error:
        materialize(tmp_cfg, model, section, plan, bad, 'synthetic-diagnostic-fixture')
    assert all(value in str(error.value) for value in ('stop', 'unknown_destination', 'unknown_nodes', 'stop:0'))
    assert not agent.calls


def test_citation_retry_receives_the_missing_endpoint_symbol_and_quote(tmp_cfg, automatic):
    from sdd.generated_visuals import generate
    section, model, _, agent = automatic
    text = 'void stop() { cancelPending(); }\n\nvoid stop() { /* no cancellation here */ }'
    source = section['design_topics'][0]['sources'][0]
    source.update(end='void stop() { /* no cancellation here */ }', sha256=hashlib.sha256(text.encode()).hexdigest())
    model.evidence['device/shutdown/stop'].update(
        text=text, sha256=source['sha256'], selector=copy.deepcopy(source), end_line=12)
    valid = copy.deepcopy(agent.draft)
    invalid = copy.deepcopy(valid)
    invalid['edges'][0]['quote_ids'] = ['stop:1']
    seen = []
    def reply(system, user, **kwargs):
        seen.append(user)
        if len(seen) == 1:
            return json.dumps(invalid)
        assert all(value in user for value in ('stop', 'cancel', 'cancelPending', 'stop:1', 'uncited_symbols'))
        return json.dumps(valid)
    agent.chat = reply
    result = generate(tmp_cfg, model, section, agent)
    assert len(seen) == 2
    assert result['records']['stop-flow']['draft'] == valid


def test_edge_label_cap_preserves_long_nodes_and_prior_valid_manuscript(tmp_cfg, automatic):
    from sdd.generated_visuals import materialize, plans, schema
    section, model, _, agent = automatic
    plan = plans(tmp_cfg, section)[0]
    long_node = 'Stop the device before releasing its remaining resources'
    draft = copy.deepcopy(agent.draft)
    draft['nodes'][0]['label_en'] = long_node
    assert materialize(tmp_cfg, model, section, plan, draft, 'test')['nodes'][0]['label_en'] == long_node
    restricted = {**plan, 'max_label_chars': 72, 'max_edge_label_chars': 20}
    with pytest.raises(ValueError, match=r'stop to cancel.label_en.*max_edge_label_chars'):
        materialize(tmp_cfg, model, section, restricted, draft, 'test')
    short = copy.deepcopy(draft)
    short['edges'][0]['label_en'] = 'Cancel waiting'
    result = materialize(tmp_cfg, model, section, restricted, short, 'test')
    assert result['nodes'][0]['label_en'] == long_node
    assert 'max_edge_label_chars' not in result
    rules = schema({'s:0': ('s', 'stop(); cancelPending();')}, 2,
                   ['stop', 'cancelPending'], 72, max_edge_label_chars=20)
    assert rules['properties']['nodes']['properties']['n0']['properties']['label_en']['maxLength'] == 72
    assert rules['properties']['edges']['items']['properties']['label_en']['maxLength'] == 20
    path = Generator(tmp_cfg, model, agent).run()[0]
    original = path.read_bytes()
    data = yaml.safe_load((tmp_cfg.root/'visuals.yaml').read_bytes())
    data['sections']['device'][0]['max_edge_label_chars'] = 8
    (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='max_edge_label_chars'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original


@pytest.mark.parametrize('value', [True, 7, 241, '20', None])
def test_edge_label_cap_rejects_invalid_configuration(tmp_cfg, automatic, value):
    from sdd.generated_visuals import inputs, plans
    section, model, _, agent = automatic
    with pytest.raises(ValueError, match='max_edge_label_chars'):
        inputs(tmp_cfg, model, section, {**plans(tmp_cfg, section)[0], 'max_edge_label_chars': value})
    assert not agent.calls


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


def test_label_retry_identifies_the_specific_field_without_relaxing_guard_validation(tmp_cfg, automatic):
    _, model, _, original = automatic
    good = json.dumps(original.draft, ensure_ascii=False)
    bad = copy.deepcopy(original.draft)
    bad['nodes'][1]['label'] = 'done=true'

    class RepairingAgent:
        def __init__(self): self.calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(bad)
            assert 'cancel.label' in user and 'done=true' in user
            assert 'condition_ref' in user and 'Current source inputs:' in user
            return good

    agent = RepairingAgent()
    paths = Generator(tmp_cfg, model, agent).run()
    assert agent.calls == 2 and paths[0].exists()


def test_while_conditions_are_opt_in_and_copy_nested_expressions_verbatim():
    from sdd.generated_visuals import condition_catalog, schema
    passages = {'loop:0': ('loop', 'while (!queue.empty(check("("))) { drain(); } if (ready) { emit(); }')}
    assert list(condition_catalog(passages).values()) == ['ready']
    extended = condition_catalog(passages, include_while=True)
    assert list(extended.values()) == ['!queue.empty(check("("))', 'ready']
    assert 'queue.empty(check("("))' not in extended.values()
    old = schema(passages, 2)['properties']['edges']['items']['properties']['condition_ref']['enum']
    new = schema(passages, 2, include_while=True)['properties']['edges']['items']['properties']['condition_ref']['enum']
    assert old == ['always','c0:true','c0:false']
    assert len(new) == 5


def test_connected_visual_checks_components_and_preserves_legacy_default(tmp_cfg, automatic):
    from sdd.generated_visuals import inputs, materialize, plans
    section, model, _, agent = automatic
    plan = plans(tmp_cfg, section)[0]
    draft = copy.deepcopy(agent.draft)
    draft['nodes'] += [dict(n, id=n['id']+'2') for n in draft['nodes']]
    draft['edges'].append(dict(draft['edges'][0], **{'from': 'stop2', 'to': 'cancel2'}))
    materialize(tmp_cfg, model, section, plan, draft, tmp_cfg.agent.label)
    plan['require_connected'] = True
    with pytest.raises(ValueError, match='disconnected IDs: cancel2, stop2'):
        materialize(tmp_cfg, model, section, plan, draft, tmp_cfg.agent.label)
    draft['edges'].append(dict(draft['edges'][0], **{'from': 'cancel', 'to': 'stop2'}))
    graph = materialize(tmp_cfg, model, section, plan, draft, tmp_cfg.agent.label)
    assert 'require_connected' not in graph
    for invalid in [1, 'true', None]:
        plan['require_connected'] = invalid
        with pytest.raises(ValueError, match='require_connected must be boolean'):
            inputs(tmp_cfg, model, section, plan)


def test_disconnected_generation_preserves_previous_manuscript(tmp_cfg, automatic):
    section, model, _, agent = automatic
    path = Generator(tmp_cfg, model, agent).run()[0]
    previous = path.read_bytes()
    visual_file = tmp_cfg.root/'visuals.yaml'
    values = yaml.safe_load(visual_file.read_text(encoding='utf-8'))
    values['sections']['device'][0]['require_connected'] = True
    visual_file.write_text(yaml.safe_dump(values, allow_unicode=True), encoding='utf-8')
    agent.draft['edges'][0]['to'] = 'stop'
    tmp_cfg.max_retries = 0
    with pytest.raises(ValueError, match='must connect every node'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == previous


def test_while_edge_requires_opt_in_and_preserves_bound_loop_guard(tmp_cfg, automatic):
    from sdd.generated_visuals import inputs, materialize, plans
    section, model, save, agent = automatic
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { while (pending()) { cancelPending(); } }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    section['design_topics'][0]['sources'][0]['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(section['design_topics'][0]['sources'][0])
    save()
    plan = plans(tmp_cfg, section)[0]
    agent.draft['edges'][0]['condition_ref'] = 'c0:true'
    with pytest.raises(ValueError, match='Unknown source condition ID'):
        materialize(tmp_cfg, model, section, plan, agent.draft, tmp_cfg.agent.label)
    plan['while_conditions'] = True
    graph = materialize(tmp_cfg, model, section, plan, agent.draft, tmp_cfg.agent.label)
    assert 'pending() [true]' in graph['edges'][0]['label']
    assert 'while_conditions' not in graph
    for invalid in ['true', 1, None]:
        plan['while_conditions'] = invalid
        with pytest.raises(ValueError, match='while_conditions must be boolean'):
            inputs(tmp_cfg, model, section, plan)


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
    assert 'Previous native draft for revision only' in agent.calls[-1][1]
    assert 'notifyStopped' in agent.calls[-1][1]  # Fresh source remains authoritative.
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
    for array in [[], [{'id':'n0','symbol':'cancel',**value}, {'id':'n1','symbol':'stop',**value}]]:
        with pytest.raises(ValueError, match='require the bound node object'):
            expand_draft({'required_symbols':['stop','cancel']}, {'nodes':array,'edges':[]}, 2)


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


@pytest.mark.parametrize('field', ['label', 'label_en'])
def test_cited_cpp_member_access_is_not_a_label_comparison(tmp_cfg, automatic, field):
    from sdd.generated_visuals import materialize, plans
    section, model, _, agent = automatic
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { cache_->put(id); data_->request()->complete(); data_->*member; value--->member; cancelPending(); }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    source = section['design_topics'][0]['sources'][0]
    source['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(source)
    plan = plans(tmp_cfg, section)[0]
    for label in ['cache_->put(id)', 'data_->request()->complete()',
                  'Call cache_->put(id) before cancelling', 'cache_->put(id) 이후 취소',
                  'data_->*member', 'value--->member']:
        draft = copy.deepcopy(agent.draft)
        draft['edges'][0][field] = label
        graph = materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')
        assert graph['edges'][0][field] == label
    # A sourced member access must not conceal a new or changed comparison.
    for label in ['cache_->put(id) > 0', 'cache_->put(id) != 0',
                  'value-->0', 'value-- > 0', 'value - > 0']:
        draft = copy.deepcopy(agent.draft)
        draft['edges'][0][field] = label
        with pytest.raises(ValueError, match='differs from cited source guards'):
            materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')


@pytest.mark.parametrize('field', ['label', 'label_en'])
def test_member_access_in_source_guard_keeps_receiver_and_arguments(tmp_cfg, automatic, field):
    from sdd.generated_visuals import materialize, plans
    section, model, _, agent = automatic
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { if (cache_->put(id) > 0) { cancelPending(); } }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    source = section['design_topics'][0]['sources'][0]
    source['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(source)
    draft = copy.deepcopy(agent.draft)
    draft['edges'][0][field] = 'cache_->put(id) > 0'
    draft['edges'][0]['condition_ref'] = 'c0:true'
    plan = plans(tmp_cfg, section)[0]
    materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')
    for label in ['other_->put(id) > 0', 'other_cache_->put(id) > 0', 'cache_.put(id) > 0',
                  'other_->cache_->put(id) > 0','cache_->put(id) > 0 + 1',
                  '(cache_->put(id) > 0) + 1','cache_->put(id) > 0 && ready()',
                  'cache_->put(other) > 0', 'cache_->put(id) >= 0']:
        draft['edges'][0][field] = label
        with pytest.raises(ValueError, match='differs from cited source guards'):
            materialize(tmp_cfg, model, section, plan, draft, 'synthetic-unit-fixture')


@pytest.mark.parametrize('operand', ['0x10','00','0u','0.','0.0','0e+2',"0'1"])
def test_cited_guard_does_not_authorize_a_prefix_of_another_numeric_operand(tmp_cfg, automatic, operand):
    from sdd.generated_visuals import materialize, plans
    section, model, _, agent = automatic
    record = model.evidence['device/shutdown/stop']
    record['text'] = 'void Device::stop() { if (ret == 0) { cancelPending(); } }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    source = section['design_topics'][0]['sources'][0]
    source['sha256'] = record['sha256']
    record['selector'] = copy.deepcopy(source)
    draft = copy.deepcopy(agent.draft)
    draft['edges'][0].update(label='ret == '+operand,condition_ref='c0:true')
    with pytest.raises(ValueError,match='differs from cited source guards'):
        materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],draft,'synthetic-unit-fixture')


@pytest.mark.parametrize('guard,label', [('ret == 0','ret = = 0'),('ret >= 0','ret > = 0'),
                                       ('ret <= 0','ret < = 0'),('ret != 0','ret ! = 0'),
                                       ('ret == 0','ret == 0 and ready()'),('ret == 0','ret == 0 or ready()'),
                                       ('ret == 0','ret == 0 bitand value'),('ret == 0','not (ret == 0)'),
                                       ('ret == 0','check(ret == 0)'),('ret == 0','check((ret == 0))')])
def test_guard_comparison_operator_keeps_lexical_boundaries(tmp_cfg,automatic,guard,label):
    from sdd.generated_visuals import materialize,plans
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']=f'void Device::stop() {{ if ({guard}) {{ cancelPending(); }} }}'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    draft=copy.deepcopy(agent.draft)
    draft['edges'][0].update(label=label,condition_ref='c0:true')
    with pytest.raises(ValueError,match='differs from cited source guards'):
        materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],draft,'synthetic-unit-fixture')


def test_edge_can_cite_split_passages_of_one_function_without_claiming_semantic_approval(tmp_cfg,automatic):
    from sdd.generated_visuals import materialize,plans,inputs
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() {\n\n    cancelPending();\n\n}'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    plan=plans(tmp_cfg,section)[0]
    passages=inputs(tmp_cfg,model,section,plan)[2]
    stop=next(k for k,(_,q) in passages.items() if 'Device::stop' in q)
    cancel=next(k for k,(_,q) in passages.items() if 'cancelPending' in q)
    assert stop!=cancel
    draft=copy.deepcopy(agent.draft)
    draft['nodes'][0]['quote_ids']=[stop]
    draft['nodes'][1]['quote_ids']=[cancel]
    draft['edges'][0]['quote_ids']=[stop,cancel]
    materialize(tmp_cfg,model,section,plan,draft,'synthetic-unit-fixture')
    draft['edges'][0]['quote_ids']=[stop]
    with pytest.raises(ValueError,match='uncited_symbols'):
        materialize(tmp_cfg,model,section,plan,draft,'synthetic-unit-fixture')

def test_identifier_v1_record_reuses_only_after_current_policy_revalidation(tmp_cfg,automatic):
    from sdd.generated_visuals import inputs,materialize,plans,generate,resolve,CITATION_BINDING_POLICY
    section,model,_,agent=automatic
    plan=plans(tmp_cfg,section)[0]
    old_pin=inputs(tmp_cfg,model,section,plan,_binding_policy='identifier-boundaries-v1')[0]
    current_pin=inputs(tmp_cfg,model,section,plan)[0]
    assert old_pin!=current_pin
    graph=materialize(tmp_cfg,model,section,plan,agent.draft,'synthetic-v1-fixture')
    record=dict(input_fingerprint=old_pin,draft=copy.deepcopy(agent.draft),graph=graph,
                producer='synthetic-v1-fixture',generation_commit='a'*40,citation_binding_policy='identifier-boundaries-v1')
    previous=_synthetic_legacy_visual_document(record)
    with pytest.raises(ValueError,match='recorded citation revalidation'):
        resolve(tmp_cfg,model,section,{'schema':1,'records':{'stop-flow':record}})
    artifact=generate(tmp_cfg,model,section,agent,previous)
    rec=artifact['records']['stop-flow']
    assert not agent.calls and rec['input_fingerprint']==old_pin
    assert rec['citation_binding_policy']=='identifier-boundaries-v1'
    assert rec['citation_binding_revalidation']==dict(policy=CITATION_BINDING_POLICY,original_input_fingerprint=old_pin,new_inference=False)
    resolve(tmp_cfg,model,section,artifact)


def test_compact_guard_display_preserves_exact_guard_and_proof(tmp_cfg, automatic):
    from sdd.generated_visuals import materialize
    from sdd.visuals import render_values
    section,model,save,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() { if (ret == 0) { stop(); cancelPending(); } }'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    section['design_topics'][0]['sources'][0]['sha256']=record['sha256']
    record['selector']=copy.deepcopy(section['design_topics'][0]['sources'][0])
    plan=yaml.safe_load((tmp_cfg.root/'visuals.yaml').read_text(encoding='utf-8'))['sections']['device'][0]
    plan['condition_display']='evidence'
    agent.draft['edges'][0].update(label='예',label_en='Yes',condition_ref='c0:true')
    graph=materialize(tmp_cfg,model,section,plan,agent.draft,'cli/test/model')
    block,source=render_values(tmp_cfg,model,section,[graph])[0][1:]
    assert graph['edges'][0]['label'].endswith('ret == 0 [true]')
    assert 'ret == 0' not in source and '#91;true#93;' in source
    assert 'ret == 0' in block.partition('??? note')[2]
    graph['edges'][0]['evidence'][0]['quote']='if (ret >= 0) { stop(); cancelPending(); }'
    with pytest.raises(ValueError):render_values(tmp_cfg,model,section,[graph])


def test_label_ceiling_is_enforced_in_schema_and_materialization(tmp_cfg, automatic):
    from sdd.generated_visuals import materialize,schema,visual_passages
    section,model,save,agent=automatic
    plan=yaml.safe_load((tmp_cfg.root/'visuals.yaml').read_text(encoding='utf-8'))['sections']['device'][0]
    plan['max_label_chars']=16
    agent.draft['nodes'][0]['label_en']='x'*17
    with pytest.raises(ValueError,match='max_label_chars'):
        materialize(tmp_cfg,model,section,plan,agent.draft,'cli/test/model')
    passages=visual_passages({'stop':model.evidence['device/shutdown/stop']['text']})[1]
    shape=schema(passages,4,max_label_chars=16)
    assert shape['properties']['nodes']['items']['properties']['label']['maxLength']==16


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


@pytest.mark.parametrize('change', [None, 'source', 'args', 'pin', 'style'])
def test_exact_legacy_cli_visual_proof_is_verified_without_rewriting_its_history(tmp_cfg, automatic, change):
    from sdd.generated_visuals import generate, resolve
    # Replay the exact historical policy; the current policy must invalidate it.
    current_style = (tmp_cfg.style_dir / 'README.md').read_bytes()
    old_style = Path(__file__).parent / 'fixtures' / 'style-before-215.txt'
    (tmp_cfg.style_dir / 'README.md').write_bytes(old_style.read_bytes())
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
    elif change == 'style':
        (tmp_cfg.style_dir / 'README.md').write_bytes(current_style)
    if change:
        with pytest.raises(ValueError):
            resolve(tmp_cfg, model, section, artifact)
    else:
        with pytest.raises(ValueError, match='recorded citation revalidation'):
            resolve(tmp_cfg, model, section, artifact)
        assert artifact == original
        updated = generate(tmp_cfg, model, section, agent,
                           _synthetic_legacy_visual_document(original['records']['stop-flow']))
        assert resolve(tmp_cfg, model, section, updated)
        for key in ('input_fingerprint','producer','draft','graph','generation_commit'):
            assert updated['records']['stop-flow'][key] == original['records']['stop-flow'][key]
        assert len(agent.calls) == 1


@pytest.mark.parametrize('label',['ret == 0이면','(ret == 0)이면','if (ret == 0)'])
def test_guard_tokens_do_not_absorb_korean_particles(tmp_cfg,automatic,label):
    from sdd.generated_visuals import materialize,plans
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() { if (ret == 0) { cancelPending(); } }'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    draft=copy.deepcopy(agent.draft)
    draft['edges'][0].update(label=label,condition_ref='c0:true')
    materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],draft,'synthetic-unit-fixture')


@pytest.mark.parametrize('mode',['label','condition_ref'])
def test_cited_fragments_cannot_synthesize_a_balanced_guard(tmp_cfg,automatic,mode):
    from sdd.generated_visuals import materialize,plans,inputs
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']=('void Device::stop() { if (ret ==\n\n0) { cancelPending(); } }'
                    '\n\nvoid other() { if (ret == 0) { audit(); } }')
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    plan=plans(tmp_cfg,section)[0]
    passages=inputs(tmp_cfg,model,section,plan)[2]
    stop=next(k for k,(_,q) in passages.items() if 'Device::stop' in q)
    cancel=next(k for k,(_,q) in passages.items() if 'cancelPending' in q)
    assert stop!=cancel
    draft=copy.deepcopy(agent.draft)
    draft['nodes'][0]['quote_ids']=[stop]
    draft['nodes'][1]['quote_ids']=[cancel]
    draft['edges'][0].update(quote_ids=[stop,cancel],condition_ref='always')
    if mode=='label':draft['edges'][0]['label']='ret == 0'
    else:draft['edges'][0]['condition_ref']='c0:true'
    with pytest.raises(ValueError,match='cited source guards|absent from its cited source passages'):
        materialize(tmp_cfg,model,section,plan,draft,'synthetic-unit-fixture')


@pytest.mark.parametrize('field',['label','label_en'])
def test_braced_expression_cannot_reuse_a_bare_source_guard(tmp_cfg,automatic,field):
    from sdd.generated_visuals import materialize,plans
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() { if (ret == 0) { cancelPending(); } }'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    draft=copy.deepcopy(agent.draft)
    draft['edges'][0].update(condition_ref='c0:true')
    draft['edges'][0][field]='bool{ret == 0}'
    with pytest.raises(ValueError,match='cited source guards'):
        materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],draft,'synthetic-unit-fixture')


@pytest.mark.parametrize('field',['label','label_en'])
@pytest.mark.parametrize('label',['sizeof ret == 0','(bool)ret == 0'])
def test_unary_or_cast_expression_is_not_the_cited_guard(tmp_cfg,automatic,field,label):
    from sdd.generated_visuals import materialize,plans
    section,model,_,agent=automatic
    record=model.evidence['device/shutdown/stop']
    record['text']='void Device::stop() { if (ret == 0) { cancelPending(); } }'
    record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
    source=section['design_topics'][0]['sources'][0]
    source['sha256']=record['sha256'];record['selector']=copy.deepcopy(source)
    draft=copy.deepcopy(agent.draft);draft['edges'][0].update(condition_ref='c0:true')
    draft['edges'][0][field]=label
    with pytest.raises(ValueError,match='cited source guards'):
        materialize(tmp_cfg,model,section,plans(tmp_cfg,section)[0],draft,'synthetic-unit-fixture')
