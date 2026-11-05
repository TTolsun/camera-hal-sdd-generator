"""Synthetic native archives test graph-only replacement, never model results."""
import copy
import hashlib
import json
import subprocess

import pytest
import yaml

from sdd.document_metadata import split_frontmatter
from sdd.generate import Generator
from sdd.generated_visuals import generate as generate_visuals
from sdd.llm import Agent
from sdd.visual_refresh import refresh
from test_generated_design import generated


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def native_replacement(tmp_cfg, generated, monkeypatch, request):
    section, model, _, prose = generated
    plan = dict(id='native-stop', topic='stop', kind='flow', generation='llm',
                title='종료 호출', question='어떤 취소 함수를 호출합니까?')
    draft = dict(nodes=[dict(id='stop', symbol='stop', label='종료', label_en='Stop',
                            shape='box', quote_ids=['stop:0']),
                        dict(id='cancel', symbol='cancelPending', label='취소', label_en='Cancel',
                             shape='box', quote_ids=['stop:0'])],
                 edges=[dict(**{'from': 'stop', 'to': 'cancel'}, label='취소 호출',
                             label_en='Calls cancellation', condition_ref='always', quote_ids=['stop:0'])])
    tmp_cfg.agent.kind='cli'
    tmp_cfg.agent.runner='claude'
    tmp_cfg.agent.model='synthetic-historical-model'
    tmp_cfg.agent.args=['--effort','high']
    tmp_cfg.agent.max_input_chars=160000
    tmp_cfg.raw['visuals']=dict(file='visuals.yaml',max_nodes=4)
    config=tmp_cfg.root/'visuals.yaml'
    mixed = getattr(request, 'param', False)
    plans = [plan, {**plan, 'id': 'native-other'}] if mixed else [plan]
    config.write_text(yaml.safe_dump(dict(schema=1,sections={'device':plans}),allow_unicode=True),encoding='utf-8')
    calls=[]
    monkeypatch.setattr('sdd.cli_agent.command',lambda cfg:['fixture-cli'])
    def run(argv,**kwargs):
        prompt=kwargs['prompt'];calls.append(prompt)
        answer=({'reviews':[dict(index=0,supported=True,reason='Synthetic source matches.')]}
                if 'Audit factual entailment' in prompt else
                draft if '"quote_ids"' in prompt else {'statements':[prose.statement]})
        return subprocess.CompletedProcess(argv,0,json.dumps(dict(
            subtype='success',is_error=False,result=json.dumps(answer))),'')
    monkeypatch.setattr('sdd.cli_agent.run',run)
    path=Generator(tmp_cfg,model,Agent(tmp_cfg.agent,tmp_cfg.build_dir/'prompts')).run()[0]
    original=path.read_bytes()
    meta,body=split_frontmatter(original.decode())
    meta['generated_visuals']['historical_annotation']=dict(review='pending',note='Original recorded value')
    meta['historical_graph_metadata']=meta['generated_visuals']
    if mixed:
        # Byte-identical source windows can retain an earlier generation commit.
        meta['generated_visuals']['records']['native-other']['generation_commit']='b'*40
        meta['generated_visuals']['records']['native-other']['historical_counter']=1
    original=('---\n'+yaml.safe_dump(meta,allow_unicode=True)+'---\n'+body).encode()
    path.write_bytes(original)
    origin=copy.deepcopy(tmp_cfg)
    (tmp_cfg.root/'original-visuals.yaml').write_bytes(config.read_bytes())
    origin.raw['visuals']['file']='original-visuals.yaml'
    if not mixed:
        tmp_cfg.agent.model='synthetic-current-model'
    plan['prompt']='Keep the same source-supported cancellation relationship.'
    config.write_text(yaml.safe_dump(dict(schema=1,sections={'device':plans}),allow_unicode=True),encoding='utf-8')
    artifact=generate_visuals(tmp_cfg,model,section,Agent(tmp_cfg.agent,tmp_cfg.build_dir/'prompts'),
                              previous=original.decode())
    if mixed:
        artifact['records']['native-other']=copy.deepcopy(meta['generated_visuals']['records']['native-other'])
    return model,path,original,origin,artifact,calls


def test_fresh_graph_records_leave_historical_prose_and_origin_intact(tmp_cfg,native_replacement):
    model,path,original,origin,artifact,calls=native_replacement
    before,_=split_frontmatter(original.decode())
    saved=copy.deepcopy(artifact);count=len(calls)
    result=refresh(tmp_cfg,model,'device',original,expected_sha256=digest(original),
                   original_cfg=origin,visual_artifact=artifact)
    after,_=split_frontmatter(result.decode())
    expected=copy.deepcopy(after['generated_design'])
    expected['body_sha256']=before['generated_design']['body_sha256']
    assert expected==before['generated_design']
    assert after['agent']==before['agent']=='cli/claude/synthetic-historical-model'
    assert after['generated_visuals']['records']==artifact['records']
    assert after['generated_visuals']['historical_annotation']==before['generated_visuals']['historical_annotation']
    assert after['historical_graph_metadata']==before['generated_visuals']
    assert after['generated_visuals']['records']['native-stop']['producer']==tmp_cfg.agent.label
    event=after['managed_visual_refresh'][-1]
    assert event['schema']==2 and event['graph_records_replaced'] is True
    assert event['original_manuscript_sha256']==digest(original)
    assert event['previous_native_records_sha256']!=event['current_native_records_sha256']
    assert 'unchanged_native_records_sha256' not in event
    assert event['new_inference'] is False and event['semantic_approval'] is False
    assert artifact==saved and path.read_bytes()==original and len(calls)==count
    # The new artifact resolves normally under its current profile; original
    # verification must still reject the old records under that new identity.
    from sdd.generated_visuals import from_manuscript
    from_manuscript(tmp_cfg,model,tmp_cfg.sections()[0],result.decode())
    assert refresh(tmp_cfg,model,'device',result,expected_sha256=digest(result),
                   original_cfg=tmp_cfg,visual_artifact=saved)==result
    assert len(calls)==count
    with pytest.raises(ValueError,match='source or question changed'):
        from_manuscript(tmp_cfg,model,tmp_cfg.sections()[0],original.decode())


@pytest.mark.parametrize('mutation',['old_profile','old_plans_removed','producer','commit','draft','missing_record','missing_origin','missing_artifact'])
def test_invalid_native_replacement_keeps_original_and_has_no_calls(tmp_cfg,native_replacement,mutation):
    model,path,original,origin,artifact,calls=native_replacement
    if mutation=='old_profile':origin.agent.model='wrong-historical-profile'
    elif mutation=='old_plans_removed':
        (origin.root/'original-visuals.yaml').write_text('schema: 1\nsections: {device: []}\n',encoding='utf-8')
    elif mutation=='producer':artifact['records']['native-stop']['producer']='false-producer'
    elif mutation=='commit':artifact['records']['native-stop']['generation_commit']='b'*40
    elif mutation=='draft':artifact['records']['native-stop']['draft']['nodes'][0]['label']='tampered label'
    elif mutation=='missing_record':artifact['records'].clear()
    elif mutation=='missing_origin':origin=None
    else:artifact=None
    count=len(calls)
    with pytest.raises(ValueError):
        refresh(tmp_cfg,model,'device',original,expected_sha256=digest(original),
                original_cfg=origin,visual_artifact=artifact)
    assert path.read_bytes()==original and len(calls)==count


@pytest.mark.parametrize('native_replacement', [True], indirect=True)
@pytest.mark.parametrize('tamper', [False, 'commit', 'counter-type'])
def test_one_new_graph_preserves_exact_validated_historical_records(tmp_cfg,native_replacement,tamper):
    model,path,original,origin,artifact,calls=native_replacement
    before,_=split_frontmatter(original.decode())
    if tamper == 'commit':
        artifact['records']['native-other']['generation_commit']='c'*40
    elif tamper == 'counter-type':
        artifact['records']['native-other']['historical_counter']=True
    count=len(calls)
    if tamper:
        with pytest.raises(ValueError,match='commit or producer'):
            refresh(tmp_cfg,model,'device',original,expected_sha256=digest(original),
                    original_cfg=origin,visual_artifact=artifact)
    else:
        result=refresh(tmp_cfg,model,'device',original,expected_sha256=digest(original),
                       original_cfg=origin,visual_artifact=artifact)
        after,_=split_frontmatter(result.decode())
        assert after['generated_visuals']['records']['native-other']==before['generated_visuals']['records']['native-other']
        assert after['generated_visuals']['records']['native-stop']['generation_commit']==model.meta['source_commit']
    assert path.read_bytes()==original and len(calls)==count
