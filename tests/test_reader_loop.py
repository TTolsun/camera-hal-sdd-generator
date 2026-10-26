import copy
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from sdd import reader_loop_policy as policy
from sdd.reader_loop import Budget, BudgetExceeded, Limits, run
from sdd.llm import Agent
from sdd.facts.model import KnowledgeModel


def verdict(kind='acceptable'):
    return dict(verdict=kind, checks={k:'pass' for k in policy.CHECKS}, findings=[], clarification='', expand=[])


@pytest.fixture
def project(tmp_cfg):
    source = tmp_cfg.source_root/'device.cpp'
    source.write_text('void stop() {\n cancelPending();\n releaseDevice();\n}\n', encoding='utf-8')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_cfg.source_root, text=True).strip()
    git('init', '-q'); git('add', '.')
    git('-c','user.name=Test','-c','user.email=test@example.com','commit','-qm','fixture')
    commit = git('rev-parse','HEAD')
    KnowledgeModel(meta={'source_commit':commit}).save(tmp_cfg.facts_path)
    source_spec = dict(id='s',file='device.cpp',start='cancelPending(',end=');',
                       scope=dict(start='void stop()',end='}'))
    section = dict(id='device',title='장치 종료',kind='prose',design_generation='llm',show_evidence=True,
        design_requirements=[dict(id='stop',question='취소와 해제 순서는 무엇입니까?')],
        design_topics=[dict(id='stop',title='종료 순서',question='취소와 해제 순서는 무엇입니까?',covers=['stop'],
            sources=[source_spec],parts=[dict(id='order',question='취소와 해제 순서는 무엇입니까?',sources=['s'])])])
    tmp_cfg.sections_file.write_text(yaml.safe_dump(dict(sections=[section]),allow_unicode=True),encoding='utf-8')
    tmp_cfg.agent.kind='ollama';tmp_cfg.agent.model='synthetic-unit-test'
    tmp_cfg.agent.max_input_chars=50000;tmp_cfg.max_retries=0
    tmp_cfg.raw['diagrams']={'enabled':False}
    return tmp_cfg


def factory(mode='repair'):
    """Synthetic responses exercise real generation, receipt/replay and checks."""
    def create(cfg, dump):
        agent=Agent(cfg,dump)
        def post(url, body):
            system,user=[m['content'] for m in body['messages']]
            if system in (policy.DIAGNOSIS_POLICY, policy.PLANNING_POLICY):
                payload=json.loads(user); pool=payload['candidates']
                expanded='releaseDevice' in pool['s:current']['text']
                result=verdict()
                if mode=='insufficient' or (system == policy.DIAGNOSIS_POLICY and not expanded):
                    result['verdict']='insufficient_evidence'
                elif not expanded or mode=='repeat':
                    cid=next((c for c in pool if ':scope' in c),'s:current')
                    result.update(verdict='repair',clarification='취소 이후 해제 호출까지 순서대로 설명하세요.',
                        expand=[cid],findings=[dict(category='coverage',candidate=cid,
                            quote='releaseDevice();',issue='The release call is missing.')])
                    result['checks']['coverage']='fail'
                if mode=='invalid':result['expand']=['invented:file']
            else:
                payload,_=json.JSONDecoder().raw_decode(user[user.index('{"reader":'):])
                passages=payload['sources']['s']; quote=next(p['quote_id'] for p in passages if 'quote_id' in p)
                expanded=any('releaseDevice' in p['text'] for p in passages)
                text=('`stop()`은 대기 요청을 취소한 뒤 장치 해제 함수를 호출합니다.' if expanded and mode!='repeat'
                      else '대기 요청을 취소하는 함수가 호출됩니다.')
                result={'statements':[dict(text=text,quote_id=quote,covers=['stop'],kind='behavior')]}
            return {'message':{'content':json.dumps(result,ensure_ascii=False)},'done':True}
        agent._post=post
        return agent
    return create


def test_loop_diagnoses_expands_regenerates_and_preserves_operational_inputs(project,tmp_path):
    before=project.sections_file.read_bytes()
    result=run(project,['device'],tmp_path/'loop',agent_factory=factory())
    assert result['stop_reason']=='model_review_complete',result
    assert len(result['rounds'])==2 and result['http_attempts']==5
    assert result['publishable'] is False and result['human_approval']=='pending'
    assert project.sections_file.read_bytes()==before and not project.sdd_dir.exists()
    final=yaml.safe_load((tmp_path/'loop/round-02/sections.yaml').read_text(encoding='utf-8'))['sections'][0]
    topic=final['design_topics'][0]
    assert topic['parts'][0]['question'].startswith('취소와 해제 순서는 무엇입니까?')
    assert topic['sources'][0]['start']=='void stop()'
    assert topic['sources'][0]['scope']==dict(start='void stop()',end='}')
    assert final['design_requirements']==yaml.safe_load(before)['sections'][0]['design_requirements']
    replay=json.loads(next((tmp_path/'loop/round-02/trial/replay-prompts/calls').rglob('*.receipt.json')).read_text())
    assert replay['http_call'] is False


@pytest.mark.parametrize(('mode','limits','reason'),[
    ('repair',Limits(max_rounds=1),'round_limit'),
    ('repair',Limits(max_calls=1),'call_limit'),
    ('repeat',Limits(max_stalls=2),'repeated_failure'),
    ('insufficient',Limits(),'insufficient_evidence'),
    ('invalid',Limits(),'invalid_or_unavailable'),
])
def test_loop_stops_without_approval(project,tmp_path,mode,limits,reason):
    result=run(project,['device'],tmp_path/'loop',limits=limits,agent_factory=factory(mode))
    assert result['stop_reason']==reason,result
    assert 'candidate_trial' not in result and result['publishable'] is False
    assert (tmp_path/'loop/loop.json').exists()


def test_budget_counts_failed_calls_and_checks_elapsed_time_before_http():
    now=[0];budget=Budget(Limits(max_calls=1,max_seconds=5),clock=lambda:now[0])
    class Broken:
        cfg=type('Cfg',(),dict(max_input_chars=100,timeout_sec=100))()
        def chat(self,*args,**kw):raise OSError('offline')
    wrapped=budget.wrap(Broken())
    with pytest.raises(OSError):wrapped.chat('x','y')
    with pytest.raises(BudgetExceeded,match='call_limit'):wrapped.chat('x','y')
    now[0]=5
    with pytest.raises(BudgetExceeded,match='time_limit'):wrapped.chat('x','y')
    assert budget.calls==1


def test_model_cannot_invent_quote_patch_gates_or_claim_unchecked_acceptance():
    pool={'s:current':dict(source='s',text='The caller must check the final configuration.')}
    result=verdict('repair');result['checks']['coverage']='fail'
    result.update(clarification='What must the caller check?',findings=[dict(category='coverage',
        candidate='s:current',quote='The caller may ignore the result.',issue='missing')])
    with pytest.raises(ValueError,match='exact source quote'):policy.validate(result,pool)
    result=verdict();result['answer_contract']={}
    with pytest.raises(ValueError,match='fields'):policy.validate(result,pool)
    result=verdict();result['checks']['coverage']='not_applicable'
    with pytest.raises(ValueError,match='explicit'):policy.validate(result,pool)


def test_expansion_cannot_escape_authorized_containing_scope(project,tmp_path):
    project.raw.setdefault('review',{})['reader_loop']={'evidence_scopes':{
        'device/stop/s':dict(start='releaseDevice(',end=');')}}
    result=run(project,['device'],tmp_path/'loop',agent_factory=factory())
    assert result['stop_reason']=='invalid_or_unavailable' and result['http_attempts']==0
    assert 'contain' in result['error']


@pytest.mark.parametrize('limits',[Limits(max_rounds=0),Limits(max_calls=True),Limits(max_seconds=-1)])
def test_invalid_limits_rejected_before_output(project,tmp_path,limits):
    with pytest.raises(ValueError):run(project,['device'],tmp_path/'loop',limits=limits)
    assert not (tmp_path/'loop').exists()


def test_existing_output_unknown_targets_and_changed_seed_are_rejected(project,tmp_path):
    out=tmp_path/'loop';out.mkdir();(out/'keep').write_text('keep')
    with pytest.raises(ValueError,match='isolated'):run(project,['device'],out)
    assert (out/'keep').read_text()=='keep'
    with pytest.raises(ValueError,match='Targets'):
        run(project,['device'],tmp_path/'new',targets=['device/unknown'])
    seed=tmp_path/'seed';seed.mkdir()
    (seed/'evaluation.json').write_text(json.dumps({'source_commit':'f'*40}))
    with pytest.raises(ValueError,match='Source commit'):
        run(project,['device'],tmp_path/'new',seed=seed)
    assert not (tmp_path/'new').exists()


def test_no_progress_and_transport_failure_are_explicit_stops(project,tmp_path):
    def no_change(cfg,dump):
        agent=factory('repeat')(cfg,dump)
        original=agent._post
        def post(url,body):
            if body['messages'][0]['content'] in (policy.DIAGNOSIS_POLICY, policy.PLANNING_POLICY):
                p=verdict('repair');p['checks']['coverage']='fail'
                p.update(expand=['s:current'],findings=[dict(category='coverage',candidate='s:current',
                    quote='cancelPending();',issue='Needs clarification')])
                return {'message':{'content':json.dumps(p)},'done':True}
            return original(url,body)
        agent._post=post
        return agent
    r=run(project,['device'],tmp_path/'no-change',agent_factory=no_change)
    assert r['stop_reason']=='no_progress' and 'candidate_trial' not in r
    def offline(cfg,dump):
        agent=Agent(cfg,dump)
        def fail(*args):raise OSError('model unavailable')
        agent._post=fail
        return agent
    r=run(project,['device'],tmp_path/'offline',agent_factory=offline)
    assert r['stop_reason']=='invalid_or_unavailable' and r['http_attempts']==1


def test_model_acceptance_does_not_override_production_failure(project,tmp_path):
    cfg=yaml.safe_load(project.sections_file.read_text(encoding='utf-8'))
    part=cfg['sections'][0]['design_topics'][0]['parts'][0]
    part['answer_contract']={'basis':'implementation','required_terms':[['releaseDevice']]}
    project.sections_file.write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
    def accepts(cfg,dump):
        agent=factory()(cfg,dump);original=agent._post
        def post(url,body):
            if body['messages'][0]['content'] in (policy.DIAGNOSIS_POLICY, policy.PLANNING_POLICY):
                return {'message':{'content':json.dumps(verdict())},'done':True}
            return original(url,body)
        agent._post=post
        return agent
    r=run(project,['device'],tmp_path/'loop',agent_factory=accepts)
    assert r['stop_reason']=='unresolved_automatic_failure'
    assert not r['rounds'][0]['automatic_passed']


def test_input_change_stops_before_next_round_and_never_exposes_candidate(project,tmp_path):
    changed=[False]
    def edits_input(cfg,dump):
        agent=factory()(cfg,dump);original=agent._post
        def post(url,body):
            if not changed[0]:
                changed[0]=True
                with project.sections_file.open('a',encoding='utf-8') as f:f.write('\n# changed during trial\n')
            return original(url,body)
        agent._post=post
        return agent
    r=run(project,['device'],tmp_path/'loop',agent_factory=edits_input)
    assert r['stop_reason']=='inputs_changed' and 'candidate_trial' not in r
    assert len(r['rounds'])==1
