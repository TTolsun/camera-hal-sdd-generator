import copy
import hashlib
import json

import pytest
import yaml

from sdd.carryover import carry_forward
from sdd.evidence import fingerprint
from sdd.export_site import export_site
from sdd.generated_design import verify
from sdd.generate import Generator
from sdd.facts.model import KnowledgeModel
from sdd.impact import compute


@pytest.mark.parametrize('focused', [False, True])
@pytest.mark.parametrize('excerpt', ['if (pending())\n    break;', 'data->queuedRequests_.push_back(request);'])
def test_scoped_draft_receives_verified_enclosing_context(generated, focused, excerpt):
    from sdd.generated_design import _unit_request
    section, model, _, _ = generated
    topic = section['design_topics'][0]
    source = topic['sources'][0]
    source.update(start=excerpt, end='\n', scope={'start': 'void stop()', 'end': '\n}'})
    context = 'void stop() {\n  auto *data = camera->_d();\n  while (active()) {\n    ' + excerpt + '\n  }\n}'
    record = model.evidence['device/stop/stop']
    record.update(text=excerpt, sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
                  context={'text': context, 'sha256': hashlib.sha256(context.encode()).hexdigest()})
    request = _unit_request(model, section, topic, 'focused' if focused else None)
    payload = (json.loads(request.user.split('근거:\n', 1)[1].split('\n질문:', 1)[0]) if focused else
               json.loads(request.user.split('\n', 1)[1])['sources'])
    item = payload['stop'][0]
    assert item['enclosing_context']['before'] + item['text'] + item['enclosing_context']['after'] == context
    assert json.dumps(context, ensure_ascii=False) not in request.user
    assert request.sources == {'stop': excerpt}
    assert request.passages == {'stop:0': ('stop', excerpt)}
    record['context']['sha256'] = '0'*64
    with pytest.raises(ValueError, match='전체 원문·해시'):
        _unit_request(model, section, topic, 'focused' if focused else None)


def test_opt_in_answer_checkpoint_is_bound_to_revision_and_question(generated, tmp_cfg, monkeypatch):
    monkeypatch.setattr('sdd.answer_cache.model_digest', lambda agent: 'original-weights')
    section, model, save, agent = generated
    tmp_cfg.raw.setdefault('review', {})['answer_cache'] = True
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 1
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 1
    model.meta['source_commit'] = 'b' * 40
    for record in model.evidence.values():
        record['commit'] = 'b' * 40
    save()
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 2
    section['design_topics'][0]['question'] = '종료 시 대기 요청이 어떻게 취소됩니까?'
    save()
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 3
    monkeypatch.setattr('sdd.answer_cache.model_digest', lambda agent: 'updated-weights')
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 4


def test_cached_answer_is_revalidated_not_treated_as_approval(generated, tmp_cfg, monkeypatch):
    monkeypatch.setattr('sdd.answer_cache.model_digest', lambda agent: 'original-weights')
    _, model, _, agent = generated
    tmp_cfg.raw.setdefault('review', {})['answer_cache'] = True
    Generator(tmp_cfg, model, agent).run()
    cache = next((tmp_cfg.build_dir/'validated-answers').glob('*.json'))
    raw = json.dumps({'statements': []})
    cache.write_text(json.dumps({'response': raw, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}))
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 2


def test_answer_checkpoint_is_disabled_by_default(generated, tmp_cfg):
    _, model, _, agent = generated
    Generator(tmp_cfg, model, agent).run()
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 2
    assert not (tmp_cfg.build_dir/'validated-answers').exists()


@pytest.fixture
def cli_units(generated, tmp_cfg, monkeypatch):
    """Synthetic completed CLI archives, never a real inference claim."""
    import subprocess
    from sdd.llm import Agent
    section, model, save, base = generated
    second = copy.deepcopy(section['design_topics'][0])
    second.update(id='prepare', title='시작 준비', question='시작 전에 무엇을 준비합니까?', covers=['startup'])
    source = dict(id='prepare', file='device.cpp', start='void prepare()', end='}')
    second['sources'] = [source]
    section['design_topics'].append(second)
    section['design_requirements'].append(dict(id='startup', question='시작 전 준비는 무엇입니까?'))
    text = 'void prepare() { enable(); }'
    model.evidence['device/prepare/prepare'] = dict(selector=source, commit='a'*40, file='device.cpp',
        line=20, end_line=20, text=text, sha256=hashlib.sha256(text.encode()).hexdigest(), status='available')
    save()
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.runner = 'claude'
    tmp_cfg.agent.model = 'fixture-model'
    tmp_cfg.agent.args = ['--effort', 'high']
    tmp_cfg.raw.setdefault('review', {})['cli_checkpoint'] = True
    calls, state = [], {'interrupt': True}
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])
    def run(argv, **kwargs):
        prompt = kwargs['prompt']
        if 'Audit factual entailment' in prompt:
            calls.append('grounding')
            raw = json.dumps({'reviews': [dict(index=0, supported=True, reason='Fixture source matches.')]})
            return subprocess.CompletedProcess(argv, 0, json.dumps(dict(subtype='success', is_error=False, result=raw)), '')
        second_unit = '시작 전에 무엇을 준비합니까?' in prompt
        calls.append('prepare' if second_unit else 'stop')
        if not second_unit and state.pop('reject_first', False):
            return subprocess.CompletedProcess(argv, 0, json.dumps(dict(subtype='success', is_error=False, result='{}')), '')
        if second_unit and state['interrupt']:
            raise RuntimeError('fixture CLI interrupted')
        statement = (dict(text='`prepare()`은 시작 전에 준비 함수를 호출합니다. 이 진입점의 호출을 처리하려면 구현자는 준비 함수와 연결된 동작을 함께 확인해야 합니다.',
                          quote=text, evidence=['prepare'], covers=['startup'], kind='behavior')
                     if second_unit else base.statement)
        raw = json.dumps({'statements': [statement]}, ensure_ascii=False)
        stdout = json.dumps(dict(subtype='success', is_error=False, result=raw))
        return subprocess.CompletedProcess(argv, 0, stdout, '')
    monkeypatch.setattr('sdd.cli_agent.run', run)
    return section, model, save, calls, state, lambda: Agent(tmp_cfg.agent, tmp_cfg.build_dir/'prompts')


def test_cli_unit_resume_preserves_validated_prefix_and_old_manuscript(cli_units, tmp_cfg):
    section, model, save, calls, state, agent = cli_units
    target = tmp_cfg.sdd_dir/'device.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('previous published manuscript', encoding='utf-8')
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run()
    assert target.read_text(encoding='utf-8') == 'previous published manuscript'
    assert calls == ['stop', 'prepare']
    assert len(list((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))) == 1
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'prepare']  # zero prefix generation calls
    artifact = yaml.safe_load(target.read_text(encoding='utf-8').split('---')[1])['generated_design']
    assert len(artifact['checkpoint_units']) == 1
    assert verify(model, section, target.read_text(encoding='utf-8'))['human_review'] == 'pending'
    reports = [json.loads(p.read_text(encoding='utf-8')) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert any('checkpoint-reused' in d['units'].values() for r in reports for d in r['documents'])


@pytest.mark.parametrize('embedded_marker', [False, True])
def test_cli_focused_retry_checkpoint_retains_exact_source_request(cli_units, tmp_cfg, embedded_marker):
    section, model, save, calls, state, agent = cli_units
    section['design_prompt'] = 'focused'
    if embedded_marker:
        section['design_topics'][0]['question'] += '\n출력: 문구는 질문 데이터입니다.'
    (tmp_cfg.prompts_dir/'focused-design-system.md').write_text('제공된 소스로 답하세요.', encoding='utf-8')
    save()
    state['reject_first'] = True
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'stop', 'prepare']
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'stop', 'prepare', 'prepare']


def test_focused_revision_after_retry_retains_a_reusable_completed_receipt(cli_units, tmp_cfg, monkeypatch):
    import subprocess
    import sdd.cli_agent as transport
    section, model, save, calls, state, agent = cli_units
    section['design_prompt'] = 'focused'
    tmp_cfg.raw['review']['design_revision'] = True
    (tmp_cfg.prompts_dir/'focused-design-system.md').write_text('제공된 소스로 답하세요.', encoding='utf-8')
    save()
    original = transport.run
    def reject_first_draft_and_revision(argv, **kwargs):
        result = original(argv, **kwargs)
        if calls[-1] == 'stop' and calls.count('stop') <= 2:
            return subprocess.CompletedProcess(argv, 0, json.dumps(dict(subtype='success', is_error=False, result='{}')), '')
        return result
    monkeypatch.setattr(transport, 'run', reject_first_draft_and_revision)
    with pytest.raises(ValueError, match='interrupted'):
        Generator(tmp_cfg, model, agent()).run()
    assert calls.count('stop') == 4
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls.count('stop') == 4  # No new draft for the validated revised unit.


def test_policy_update_does_not_hide_other_compatible_disk_checkpoints(cli_units, tmp_cfg, monkeypatch):
    from sdd.cli_checkpoint import UnitStore
    section, model, save, calls, state, agent = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    before = list(calls)
    UnitStore._indexes.clear()  # A new process starts with disk checkpoints only.
    section['design_topics'][1]['title'] = '시작 준비의 새 제목'
    save()
    monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'updated': 'validator'})
    Generator(tmp_cfg, model, agent()).run()
    assert calls == before


def test_changed_prior_answer_revalidates_later_cached_units_without_redrafting(cli_units, tmp_cfg, monkeypatch):
    import subprocess
    import sdd.cli_agent as transport
    section, model, save, calls, state, agent = cli_units
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    section['design_topics'][0]['question'] += ' 정지 진입점의 책임을 확인하세요.'
    save()
    original = transport.run
    def updated_wording(argv, **kwargs):
        result = original(argv, **kwargs)
        if calls[-1] == 'stop':
            native = json.loads(result.stdout)
            data = json.loads(native['result'])
            data['statements'][0]['text'] = data['statements'][0]['text'].replace('종료 시', '정지할 때')
            native['result'] = json.dumps(data, ensure_ascii=False)
            return subprocess.CompletedProcess(argv, 0, json.dumps(native), '')
        return result
    monkeypatch.setattr(transport, 'run', updated_wording)
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'stop']
    reports = [json.loads(p.read_text(encoding='utf-8')) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert any(r['documents'][0]['units']['device_prepare'] == 'checkpoint-revalidated' for r in reports)


@pytest.mark.parametrize('change', ['local-check', 'title'])
def test_focused_local_validation_or_heading_change_does_not_redraft_other_units(cli_units, tmp_cfg, change):
    section,model,save,calls,state,agent=cli_units
    section['design_prompt']='focused'
    topic=section['design_topics'][0]
    topic['answer_contract']=dict(basis='description',reject_patterns=[])
    (tmp_cfg.prompts_dir/'focused-design-system.md').write_text('제공된 소스로 답하세요.',encoding='utf-8')
    save()
    with pytest.raises(ValueError):Generator(tmp_cfg,model,agent()).run()
    if change=='local-check':
        topic['answer_contract']['reject_patterns'].append(dict(pattern='unsupported-guarantee',message='Unsupported guarantee.'))
    else:topic['title']='같은 종료 책임의 새 제목'
    save();state['interrupt']=False
    Generator(tmp_cfg,model,agent()).run()
    assert calls==['stop','prepare','prepare']


@pytest.mark.parametrize('change', ['checksum', 'receipt', 'stdout', 'missing-review', 'statements'])
def test_cli_checkpoint_damage_fails_and_preserves_old_output(cli_units, tmp_cfg, change):
    _, model, _, calls, state, agent = cli_units
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, agent()).run()
    cache = next((tmp_cfg.build_dir/'cli-checkpoints').glob('*.json'))
    data = json.loads(cache.read_text(encoding='utf-8'))
    if change == 'checksum':
        data['sha256'] = 'bad'
    elif change in ('missing-review', 'statements'):
        if change == 'missing-review':
            data['payload']['receipts'] = []
        else:
            data['payload']['statements'][0]['text'] = 'tampered validated statement'
        from sdd.cli_checkpoint import checksum
        data['sha256'] = checksum(data['payload'])
    elif change == 'receipt':
        receipt = tmp_cfg.build_dir/'prompts/calls'/data['payload']['receipts'][0]
        receipt.write_text('{}', encoding='utf-8')
    else:
        receipt = tmp_cfg.build_dir/'prompts/calls'/data['payload']['receipts'][0]
        saved_receipt = json.loads(receipt.read_text(encoding='utf-8'))
        stdout = tmp_cfg.build_dir/'prompts'/saved_receipt['provider']['stdout_path']
        stdout.write_text('tampered', encoding='utf-8')
    cache.write_text(json.dumps(data), encoding='utf-8')
    state['interrupt'] = False
    before = len(calls)
    with pytest.raises(ValueError, match='checkpoint'):
        Generator(tmp_cfg, model, agent()).run()
    assert len(calls) == before


@pytest.mark.parametrize('change', ['commit', 'question', 'evidence', 'model', 'args', 'policy', 'rendering', 'style'])
def test_cli_checkpoint_input_changes_require_fresh_calls(cli_units, tmp_cfg, monkeypatch, change):
    section, model, save, calls, state, agent = cli_units
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, agent()).run()
    if change == 'commit':
        model.meta['source_commit'] = 'b'*40
        for row in model.evidence.values():
            row['commit'] = 'b'*40
    elif change == 'question':
        section['design_topics'][0]['question'] += ' 조건을 설명하세요.'
    elif change == 'evidence':
        row = model.evidence['device/stop/stop']
        row['text'] += ' // changed source'
        row['sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
    elif change == 'policy':
        monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'changed': 'policy'})
    elif change == 'rendering':
        tmp_cfg.raw['site'] = {'title': 'A different presentation title'}
    elif change == 'style':
        path = tmp_cfg.style_dir/'README.md'
        path.write_text(path.read_text(encoding='utf-8')+'\n전역 집필 규칙 변경입니다.\n', encoding='utf-8')
    else:
        setattr(tmp_cfg.agent, change, 'other-model' if change == 'model' else ['--effort', 'medium'])
    save()
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls.count('stop') == (1 if change in ('policy', 'rendering') else 2)


def test_cli_changed_grounding_policy_reviews_saved_draft_without_regenerating(cli_units, tmp_cfg, monkeypatch):
    _, model, _, calls, state, agent = cli_units
    tmp_cfg.raw['review']['design_grounding'] = True
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'grounding', 'prepare']
    monkeypatch.setattr('sdd.grounding.policy_hash', lambda: 'new-grounding-policy')
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'grounding', 'prepare', 'grounding', 'prepare', 'grounding']
    from sdd.document_metadata import split_frontmatter
    metadata, _ = split_frontmatter((tmp_cfg.sdd_dir/'device.md').read_text(encoding='utf-8'))
    resumed = metadata['generated_design']['checkpoint_units'][0]
    assert resumed['new_grounding_review'] and len(resumed['receipts']) == 3
    current = json.loads((tmp_cfg.build_dir/'cli-checkpoints'/resumed['checkpoint']).read_text(encoding='utf-8'))
    assert resumed['receipts'] == current['payload']['receipts']


def test_same_source_changed_validator_facts_revalidate_without_redrafting(cli_units, tmp_cfg):
    from sdd.facts.model import ClassInfo
    _, model, save, calls, state, agent = cli_units
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, agent()).run()
    model.classes['NewClass'] = ClassInfo('NewClass', bases=['Base'])
    save()
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'prepare']
    reports = [json.loads(p.read_text(encoding='utf-8')) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert any(r['documents'][0]['units']['device_stop'] == 'checkpoint-revalidated' for r in reports)


def test_changed_typography_policy_revalidates_and_updates_saved_statements(cli_units, tmp_cfg, monkeypatch):
    import sdd.design_response as response
    _, model, _, calls, state, agent = cli_units
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, agent()).run()
    original = response.normalize_answer
    def normalize(model, statements, sources):
        original(model, statements, sources)
        for statement in statements:
            statement['text'] = statement['text'].replace('`stop()`', '`stop`')
    monkeypatch.setattr(response, 'normalize_answer', normalize)
    monkeypatch.setattr('sdd.cli_checkpoint.validation_policy', lambda: {'typography': 'updated'})
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'prepare']
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare', 'prepare']
    caches = [json.loads(p.read_text(encoding='utf-8'))['payload']
              for p in (tmp_cfg.build_dir/'cli-checkpoints').glob('*.json')]
    stop = next(p for p in caches if p['identity']['topic']['id'] == 'stop')
    assert stop['statements'][0]['text'].startswith('`stop`')


def test_cli_budget_exhaustion_preserves_prefix_and_reports_not_started(cli_units, tmp_cfg):
    _, model, _, calls, state, agent = cli_units
    tmp_cfg.raw['review']['max_calls'] = 1
    with pytest.raises(ValueError, match='budget exhausted'):
        Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop']
    tmp_cfg.raw['review']['max_calls'] = 2
    state['interrupt'] = False
    Generator(tmp_cfg, model, agent()).run()
    assert calls == ['stop', 'prepare']


def test_cli_checkpoint_persistence_failure_stops_before_replacing_output(cli_units, tmp_cfg, monkeypatch):
    _, model, _, calls, _, agent = cli_units
    path=tmp_cfg.sdd_dir/'device.md'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('old output',encoding='utf-8')
    def fail(*args,**kwargs):raise PermissionError('fixture persistence failure')
    monkeypatch.setattr('sdd.cli_checkpoint.save',fail)
    with pytest.raises(ValueError,match='persistence failed'):
        Generator(tmp_cfg,model,agent()).run()
    assert calls==['stop']
    assert path.read_text(encoding='utf-8')=='old output'


def test_time_budget_includes_validation_and_cached_units(tmp_cfg):
    from sdd.generation_run import Execution, BudgetExceeded
    now=[0]
    tmp_cfg.raw.setdefault('review',{})['max_seconds']=1
    execution=Execution(tmp_cfg,object(),clock=lambda:now[0])
    with pytest.raises(BudgetExceeded,match='time budget'):
        with execution.document('device',['stop']):
            execution.unit('stop','checkpoint-reused')
            now[0]=2
    assert execution.report['calls']==[]
    assert execution.report['documents'][0]['failure_kind']=='budget'


@pytest.mark.parametrize('scope', ['max_seconds', 'document_max_seconds'])
@pytest.mark.parametrize('finished', [0.95, 1.05])
def test_subsecond_remaining_time_never_accepts_a_response_after_deadline(tmp_cfg, scope, finished):
    from sdd.generation_run import Execution, BudgetExceeded
    now, timeouts = [0.0], []
    tmp_cfg.raw.setdefault('review', {})[scope] = 1
    timeout = tmp_cfg.agent.timeout_sec
    class Agent:
        def chat(self, *args, **kwargs):
            timeouts.append(tmp_cfg.agent.timeout_sec)
            now[0] = finished
            return 'completed response'
    execution = Execution(tmp_cfg, Agent(), clock=lambda: now[0])
    def invoke():
        with execution.document('device', ['stop']):
            now[0] = 0.9
            return execution.chat('system', 'user')
    if finished > 1:
        with pytest.raises(BudgetExceeded, match='time budget'):
            invoke()
        assert execution.report['calls'][0]['status'] == 'failed'
        assert execution.report['calls'][0]['failure_kind'] == 'budget'
    else:
        assert invoke() == 'completed response'
        assert execution.report['calls'][0]['status'] == 'completed'
    assert timeouts == [pytest.approx(0.1)]
    assert tmp_cfg.agent.timeout_sec == timeout


def test_single_required_contract_cannot_decode_as_only_a_limitation():
    from sdd.generated_design import response_schema
    topic = dict(covers=['lifetime'], _max_statements=1, answer_contract=dict(basis='contract'))
    def kinds(t):
        return response_schema(t)['properties']['statements']['items']['properties']['kind']['enum']
    assert kinds(topic) == ['behavior']
    # Optional uncertainty still belongs in genuinely multi-statement answers.
    assert kinds({**topic, '_max_statements': 2}) == ['behavior']
    assert kinds({**topic, '_max_statements': 2, 'answer_contract': {'basis': 'description'}}) == ['behavior', 'limitation']
    assert kinds(dict(covers=['lifetime'])) == ['behavior', 'limitation']


@pytest.fixture
def generated(tmp_cfg):
    source = dict(id='stop', file='device.cpp', start='void stop()', end='}')
    text = 'void stop() { cancelPending(); }'
    section = dict(id='device', title='장치 개요', design_generation='llm',
                   design_requirements=[dict(id='shutdown', question='대기 요청은 어떻게 반환됩니까?')],
                   design_topics=[dict(id='stop', title='종료 책임', question='종료 책임을 설명하세요.',
                                       covers=['shutdown'], sources=[source])],
                   next=dict(title='장치 개요', link='device.md'), show_evidence=True)
    model = KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence={
        'device/stop/stop': dict(selector=source, commit='a' * 40, file='device.cpp', line=10, end_line=10,
                               text=text, sha256=hashlib.sha256(text.encode()).hexdigest(), status='available')})
    def save():
        tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
        model.save(tmp_cfg.facts_path)
    save()
    tmp_cfg.agent.kind = 'ollama'
    tmp_cfg.agent.max_input_chars = 18000
    statement = dict(quote=text, text='`stop()`은 종료 시 대기 중인 요청을 취소하는 함수를 호출합니다. 구현자는 이 종료 진입점에서 요청 취소 처리가 시작된다는 점을 확인하고 해당 처리 함수의 구현을 함께 읽어야 합니다.', evidence=['stop'], covers=['shutdown'], kind='behavior')
    class Agent:
        def __init__(self):
            self.calls = []
            self.statement = copy.deepcopy(statement)
        def chat(self, system, user, **kw):
            self.calls.append(user)
            # A previous factual few-shot example leaked into unrelated stop
            # answers. Policy must not supply an unrelated buffer-lifetime fact.
            assert 'retain the buffer until completion' not in system
            assert '호출자는 완료될 때까지 버퍼를 유지해야 합니다' not in system
            return json.dumps({'statements': [self.statement]}, ensure_ascii=False)
    return section, model, save, Agent()


@pytest.mark.parametrize('kind,structured,label', [
    ('cli', True, 'cli/hermes/test-model'),
    ('ollama', True, 'ollama/test-model'),
    ('response-bundle', True, 'response-bundle/test-model'),
    ('openai-compatible', False, 'openai-compatible/test-model'),
])
def test_generate_uses_explicit_dependencies_and_transport_policy(tmp_cfg, generated, kind, structured, label):
    from sdd.generated_design import generate
    section, model, _, agent = generated
    tmp_cfg.agent.kind = kind
    tmp_cfg.agent.model = 'test-model'
    calls = []
    chat = agent.chat
    def capture(system, user, **kwargs):
        calls.append(kwargs)
        return chat(system, user, **kwargs)
    agent.chat = capture
    pinned, resolved, report, artifact = generate(tmp_cfg, model, agent, section)
    assert len(calls) == 1
    assert ('response_schema' in calls[0]) is structured
    assert calls[0]['tag'] == 'device_stop_0'
    assert pinned is not model
    assert resolved['design_topics'][0]['statements'][0]['quote'] == 'void stop() { cancelPending(); }'
    assert report['human_review'] == 'pending'
    assert artifact['topic_agents'] == {'stop': label}
    assert not tmp_cfg.sdd_dir.exists()


def test_generate_export_and_carryover_required_llm_answers(tmp_cfg, generated):
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8')
    assert len(agent.calls) == 1
    assert 'cancelPending' in agent.calls[0]
    assert 'generation_method: facts-and-llm' in text
    assert 'agent: ollama/' in text
    assert 'statements' not in section['design_topics'][0]
    assert verify(model, section, text)['human_review'] == 'pending'
    export_site(tmp_cfg)
    model.meta['source_commit'] = 'b' * 40
    model.evidence['device/stop/stop']['commit'] = 'b' * 40
    save()
    promoted, stale = carry_forward(tmp_cfg, model, [])
    assert promoted == [path] and not stale
    export_site(tmp_cfg)


def test_response_bundle_generates_then_rejects_changed_source(tmp_cfg, generated, tmp_path):
    from sdd.llm import Agent
    section, model, save, draft = generated
    path = Generator(tmp_cfg, model, draft).run()[0]
    original = path.read_bytes()
    tmp_cfg.agent.kind = 'response-bundle'
    tmp_cfg.agent.response_dir = str(tmp_path / 'responses')
    agent = Agent(tmp_cfg.agent)
    with pytest.raises(ValueError, match='현재 입력'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original
    request_path = next((tmp_path / 'responses').glob('*.request.json'))
    request = json.loads(request_path.read_text(encoding='utf-8'))
    response = {k: request[k] for k in ('schema', 'model', 'request_sha256')}
    response['response'] = json.dumps({'statements': [draft.statement]}, ensure_ascii=False)
    request_path.with_name(request_path.name.replace('.request.', '.response.')).write_text(
        json.dumps(response, ensure_ascii=False), encoding='utf-8')
    Generator(tmp_cfg, model, agent).run()
    text = path.read_text(encoding='utf-8')
    assert 'agent: response-bundle/' in text
    assert verify(model, section, text)['human_review'] == 'pending'
    original = path.read_bytes()
    record = model.evidence['device/stop/stop']
    record['text'] = 'void stop() { if (ready) cancelPending(); }'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    save()
    with pytest.raises(ValueError, match='현재 입력'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='재생성'):
        export_site(tmp_cfg)


def test_required_contract_schema_does_not_mislabel_prohibitions_as_unknown():
    from sdd.generated_design import response_schema
    topic = {'covers':['lifetime'], 'answer_contract':{'basis':'contract'}}
    schema = response_schema(topic, {'source:0': ('source', 'shall not access the request')})
    assert schema['properties']['statements']['items']['properties']['kind']['enum'] == ['behavior']
    assert 'minItems' not in schema['properties']['statements']  # No evidence can still return no answer.
    topic['answer_contract']['basis'] = 'description'
    assert response_schema(topic)['properties']['statements']['items']['properties']['kind']['enum'] == ['behavior','limitation']


@pytest.mark.parametrize('bad', [0, 9, True, '3'])
def test_invalid_part_answer_budget_fails_before_generation(tmp_cfg, generated, bad):
    section, model, save, agent = generated
    section['design_topics'][0]['parts'] = [dict(id='one', question='종료 동작은 무엇입니까?',
        sources=['stop'], max_statements=bad)]
    save()
    with pytest.raises(ValueError, match='max_statements'):
        Generator(tmp_cfg, model, agent).run()


@pytest.mark.parametrize('maximum', [None, 4])
def test_parts_limit_sources_and_keep_all_answers(tmp_cfg, generated, maximum):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    second = dict(id='drain', file='device.cpp', start='void drain()', end='}')
    topic['sources'].append(second)
    source = 'void drain() { drainQueue(); }'
    model.evidence['device/stop/drain'] = dict(selector=second, commit='a' * 40, file='device.cpp',
        line=20, end_line=20, text=source, sha256=hashlib.sha256(source.encode()).hexdigest(), status='available')
    topic['parts'] = [dict(id='cancel', question='취소 책임은 무엇입니까?', sources=['stop']),
                      dict(id='drain', question='비우는 책임은 무엇입니까?', sources=['drain'])]
    if maximum is not None:
        for part in topic['parts']:
            part['max_statements'] = maximum
    save()
    class PartAgent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            assert '대기 요청은 어떻게 반환됩니까?' not in user
            assert kw['response_schema']['properties']['statements']['maxItems'] == (maximum or 2)
            statement = copy.deepcopy(base_agent.statement)
            if 'drainQueue' in user:
                assert 'cancelPending' not in user
                statement.update(quote=source, evidence=['drain'],
                    text='`drain()`은 대기 큐를 비우는 함수를 호출합니다. 큐를 비우는 동작의 세부 조건은 호출된 함수의 구현에서 확인해야 합니다.')
            else:
                assert 'drainQueue' not in user
            return json.dumps({'statements': [statement]}, ensure_ascii=False)
    agent = PartAgent()
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8')
    assert len(agent.calls) == 2 and 'drainQueue' in text and 'cancelPending' in text
    assert verify(model, section, text)['human_review'] == 'pending'
    original = path.read_bytes()
    topic['parts'][1]['sources'] = ['missing']
    save()
    with pytest.raises(ValueError, match='parts'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original and len(agent.calls) == 2


@pytest.mark.parametrize('prompt_mode', ['standard', 'focused'])
def test_part_contract_retry_and_saved_answer_revalidation(tmp_cfg, generated, prompt_mode):
    tmp_cfg.raw['review'] = {'design_prompt': prompt_mode}
    (tmp_cfg.prompts_dir / 'focused-design-system.md').write_text('각 질문에 답하세요.', encoding='utf-8')
    from sdd.export_html import _split
    section, model, save, agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='cancel', question='호출자의 취소 의무는 무엇입니까?', sources=['stop'],
                          answer_contract=dict(basis='contract', required_terms=[['cancelPending']]))]
    save()
    rejected = '종료는 언제나 안전합니다.'
    valid = '호출자는 `cancelPending()`으로 취소 처리를 시작해야 합니다.'
    class RetryAgent:
        calls = []
        def chat(self, system, user, **kw):
            if prompt_mode == 'focused':
                assert system == '각 질문에 답하세요.'
                assert kw['response_schema']['properties']['statements']['maxItems'] == 1
            self.calls.append(user)
            response = copy.deepcopy(agent.statement)
            response['text'] = rejected if len(self.calls) == 1 else valid
            return json.dumps({'statements': [response]}, ensure_ascii=False)
    retry = RetryAgent()
    path = Generator(tmp_cfg, model, retry).run()[0]
    assert len(retry.calls) == 2
    assert (rejected in retry.calls[1]) is (prompt_mode == 'standard')
    assert '원문' in retry.calls[1] or '근거:' in retry.calls[1]
    assert '필수 용어 누락' in retry.calls[1]
    manuscript = path.read_text(encoding='utf-8')
    meta, body = _split(manuscript)
    assert meta['generated_design']['answers']['stop'][0]['part_id'] == 'cancel'
    # A stored answer cannot remove its part identity even if a body hash still matches.
    meta['generated_design']['answers']['stop'][0].pop('part_id')
    tampered = '---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body
    with pytest.raises(ValueError, match='id'):
        verify(model, section, tampered)
    original = path.read_bytes()
    topic['parts'][0]['answer_contract']['required_terms'].append(['missingRequirement'])
    save()
    with pytest.raises(ValueError, match='재생성'):
        export_site(tmp_cfg)
    with pytest.raises(ValueError, match='필수 용어 누락'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original


def test_cited_caller_check_obligation_is_a_valid_answer(tmp_cfg, generated):
    section, model, save, agent = generated
    quote = 'The caller shall check the configuration carefully.'
    record = model.evidence['device/stop/stop']
    record.update(text=quote, sha256=hashlib.sha256(quote.encode()).hexdigest())
    section['design_topics'][0]['answer_contract'] = dict(basis='contract')
    agent.statement.update(quote=quote, text='호출자는 조정된 설정을 다시 확인해야 합니다.')
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    verify(model, section, path.read_text(encoding='utf-8'))


def test_impact_reuses_only_unchanged_topics_and_preserves_origin(tmp_cfg, generated):
    from sdd.impact import ImpactReport
    from sdd.export_html import _split
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    first = _split(path.read_text(encoding='utf-8'))[0]
    report = ImpactReport(base='a' * 40, head='b' * 40, sections=['device'])
    tmp_cfg.agent.model = 'new-model'
    agent.calls.clear()
    Generator(tmp_cfg, model, agent).run(impact=report)
    assert not agent.calls
    meta = _split(path.read_text(encoding='utf-8'))[0]
    assert meta['agent'] == first['agent']
    assert meta['generated_design']['reused_topics'] == ['stop']
    section['design_topics'][0]['question'] += ' 반환 조건도 설명하세요.'
    save()
    Generator(tmp_cfg, model, agent).run(impact=report)
    assert len(agent.calls) == 1
    assert _split(path.read_text(encoding='utf-8'))[0]['generated_design']['generated_topics'] == ['stop']
    record = model.evidence['device/stop/stop']
    record['text'] += ' // updated source'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    save()
    Generator(tmp_cfg, model, agent).run(impact=report)
    assert len(agent.calls) == 2
    # Explicit generation still requests a new answer, even without source changes.
    Generator(tmp_cfg, model, agent).run()
    assert len(agent.calls) == 3


def test_legacy_reuse_cannot_invent_missing_prompt_and_model_identity(tmp_cfg, generated):
    from sdd.design_reuse import reusable, topic_inputs
    from sdd.export_html import _split
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    meta, body = _split(path.read_text(encoding='utf-8'))
    artifact = meta['generated_design']
    for key in ('topic_inputs', 'topic_agents', 'reused_topics', 'generated_topics'):
        artifact.pop(key)
    legacy = '---\n' + '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False) if k == "generated_design" else v}'
                                for k, v in meta.items()) + '\n---\n' + body
    inputs = topic_inputs(model, section, 'policy')
    assert not reusable(model, section, legacy, inputs)[0]
    assert not reusable(model, section, legacy + 'tampered', inputs)[0]
    section['design_topics'][0]['question'] += ' changed'
    assert not reusable(model, section, legacy, topic_inputs(model, section, 'policy'))[0]


@pytest.mark.parametrize('quote', ['*\n' * 8, ' * \n' * 8])
def test_comment_decoration_cannot_be_used_as_source_evidence(generated, quote):
    from sdd.design_response import materialize
    section, model, _, agent = generated
    statement = {**agent.statement, 'quote': quote}
    with pytest.raises(ValueError, match='원문 구절 quote'):
        materialize(model, section, {'stop': [statement]})
    statement['evidence'] = ['nonexistent']
    with pytest.raises(ValueError, match='원문 구절 quote'):
        materialize(model, section, {'stop': [statement]})


def test_unpartitioned_response_obeys_its_declared_schema_limit(generated):
    from sdd.design_response import decode_unit
    section, model, _, agent = generated
    topic = section['design_topics'][0]
    raw = json.dumps({'statements': [agent.statement] * 9})
    with pytest.raises(ValueError, match='8문단'):
        decode_unit(model, section, topic, raw, {}, {})


def test_structural_change_rebuilds_page_without_rewriting_unchanged_source_prose(tmp_cfg, generated):
    from sdd.facts.model import ClassInfo
    from sdd.impact import ImpactReport
    section, model, save, agent = generated
    section['facts'] = {'classes': ['Device'], 'class_table': False}
    model.classes['Device'] = ClassInfo('Device', brief='Before structural extraction')
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    old_fingerprint = fingerprint(model, section)
    model.classes['Device'].brief = 'After structural extraction'
    record = model.evidence['device/stop/stop']
    record.update(line=11, end_line=11)
    save()
    assert fingerprint(model, section) != old_fingerprint
    agent.calls.clear()
    Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='b'*40, sections=['device']))
    assert not agent.calls
    verify(model, section, path.read_text(encoding='utf-8'))
    assert 'device.cpp:11' in path.read_text(encoding='utf-8')
    record = model.evidence['device/stop/stop']
    record['text'] += ' // Changed evidence still requires generation'
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    save()
    Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='b'*40, sections=['device']))
    assert len(agent.calls) == 1


@pytest.mark.parametrize('extension', ['frag', 'vert', 'comp'])
def test_generated_shader_explanation_is_cited_and_exported(tmp_cfg, generated, extension):
    from sdd.validate import check
    section, model, save, agent = generated
    filename = f'shaders/process.{extension}'
    section['design_topics'][0]['sources'][0]['file'] = filename
    model.evidence['device/stop/stop']['file'] = filename
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8')
    assert f'`{filename}:10`' in text
    assert verify(model, section, text)['status'] == 'documented'
    export_site(tmp_cfg)
    allowed = {f'{filename}:10'}
    verdict = check(f'설명 ' * 40 + f'`{filename}:10` `https://wrong/{filename}:10`', allowed)
    assert not verdict.ok and verdict.invalid == [f'https://wrong/{filename}:10']


@pytest.mark.parametrize('change', ['missing', 'wrong_source', 'wrong_quote', 'wrong_question', 'limitation', 'uncertainty', 'uncited_paragraph', 'html'])
def test_failed_llm_answer_preserves_all_pages(tmp_cfg, generated, change):
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    original = path.read_bytes()
    if change == 'missing': agent.statement['text'] = ''
    if change == 'wrong_source': agent.statement['evidence'] = ['not-supplied']
    if change == 'wrong_quote': agent.statement['quote'] = 'This text is not in the source.'
    if change == 'wrong_question': agent.statement['covers'] = ['unknown']
    if change == 'limitation': agent.statement['kind'] = 'limitation'
    if change == 'uncertainty': agent.statement['text'] = '해당 구현의 종료 동작과 취소 처리 조건은 이 발췌만으로 확인할 수 없습니다.'
    if change == 'uncited_paragraph': agent.statement['text'] = '첫 문단입니다.\n\n두 번째 문단입니다.'
    if change == 'html': agent.statement['text'] = '<script>bad()</script>'
    early = dict(id='early', title='먼저 생성', kind='table')
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [early, section]}, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='LLM'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original
    assert not (tmp_cfg.sdd_dir / 'early.md').exists()


@pytest.mark.parametrize('change', ['text', 'question', 'source', 'missing_record'])
def test_export_revalidates_llm_record(tmp_cfg, generated, change):
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    export_site(tmp_cfg)
    manifest = (tmp_cfg.build_dir / 'site/site-manifest.json').read_bytes()
    if change == 'text':
        path.write_text(path.read_text(encoding='utf-8').replace('취소하는', '보존하는'), encoding='utf-8')
    elif change == 'question':
        section['design_requirements'][0]['question'] = '새 질문입니다.'
    elif change == 'source':
        model.evidence['device/stop/stop']['text'] += '\n// new code'
        model.evidence['device/stop/stop']['sha256'] = hashlib.sha256(model.evidence['device/stop/stop']['text'].encode()).hexdigest()
    else:
        path.write_text('\n'.join(l for l in path.read_text(encoding='utf-8').split('\n') if not l.startswith('generated_design:')), encoding='utf-8')
    save()
    with pytest.raises(ValueError, match='LLM'):
        export_site(tmp_cfg)
    assert (tmp_cfg.build_dir / 'site/site-manifest.json').read_bytes() == manifest


def test_repeated_answer_is_rejected(tmp_cfg, generated):
    section, model, save, agent = generated
    from sdd.generated_design import materialize
    with pytest.raises(ValueError, match='중복'):
        materialize(model, section, {'stop': [agent.statement, agent.statement]})


def test_real_quote_with_another_valid_source_is_rejected(tmp_cfg, generated):
    section, model, save, agent = generated
    other = dict(id='other', file='other.cpp', start='void flush()', end='}')
    section['design_topics'][0]['sources'].append(other)
    text = 'void flush() { flushBuffers(); }'
    model.evidence['device/stop/other'] = dict(selector=other, commit='a' * 40,
        file='other.cpp', line=1, end_line=1, text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(), status='available')
    save()
    agent.statement['evidence'] = ['other']
    with pytest.raises(ValueError, match='실제 원문과 일치하지 않습니다'):
        Generator(tmp_cfg, model, agent).run()
    assert not (tmp_cfg.sdd_dir / 'device.md').exists()


def test_passage_selection_resolves_real_quote_and_source(tmp_cfg, generated):
    section, model, save, agent = generated
    statement = {k: v for k, v in agent.statement.items() if k not in {'quote', 'evidence'}}
    statement['quote_id'] = 'stop:0'
    agent.statement = statement
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8')
    assert verify(model, section, text)['status'] == 'documented'
    assert 'cancelPending' in text and 'device.cpp:10' in text
    export_site(tmp_cfg)
    original = path.read_bytes()
    agent.statement['quote_id'] = 'stop:999'
    with pytest.raises(ValueError, match='제공되지 않은 quote_id'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original


def test_response_schema_preserves_cpp_operators_but_rejects_html(tmp_cfg, generated):
    from sdd.generated_design import response_schema, materialize
    section, model, _, agent = generated
    assert response_schema(section['design_topics'][0])['properties']['statements']['items']['properties']['text']['type'] == 'string'
    agent.statement['text'] = '`request->_d()->cancel()`과 `std::unique_ptr<Request>`를 사용합니다.'
    _, resolved = materialize(model, section, {'stop': [agent.statement]})
    assert resolved['design_topics'][0]['statements'][0]['text'] == agent.statement['text']
    agent.statement['text'] = '<script>alert(1)</script>'
    with pytest.raises(ValueError, match='HTML'):
        materialize(model, section, {'stop': [agent.statement]})


def test_short_source_bound_answer_does_not_need_padding(tmp_cfg, generated):
    from sdd.generated_design import validate_answers
    section, model, _, agent = generated
    agent.statement['text'] = '`stop()`은 대기 큐를 비웁니다.'
    part = copy.deepcopy(section)
    part['design_topics'][0]['_part_id'] = 'one-contract'
    validate_answers(model, part, {'stop': [agent.statement]})
    validate_answers(model, section, {'stop': [agent.statement]})


def test_question_identifier_can_receive_code_typography():
    from sdd.facts.model import ClassInfo
    from sdd.generated_design import normalize_answer
    model = KnowledgeModel(classes={'ns::Manager': ClassInfo('ns::Manager')})
    statements = [{'text': 'Manager는 장치를 열거합니다.'}]
    normalize_answer(model, statements, ['The manager enumerates devices.', 'Manager의 역할은 무엇입니까?'])
    assert statements[0]['text'] == '`Manager`는 장치를 열거합니다.'


def test_exhausted_thinking_budget_preserves_manuscript(tmp_cfg, generated, monkeypatch):
    from sdd.llm import Agent
    section, model, save, fake = generated
    path = Generator(tmp_cfg, model, fake).run()[0]
    original = path.read_bytes()
    agent = Agent(tmp_cfg.agent)
    calls = []
    def exhausted(url, body):
        calls.append(body)
        return {'message': {'content': ''}, 'done_reason': 'length'}
    monkeypatch.setattr(agent, '_post', exhausted)
    with pytest.raises(ValueError, match='출력 토큰 한도'):
        Generator(tmp_cfg, model, agent).run()
    assert len(calls) == 1
    assert path.read_bytes() == original


def test_source_revision_is_validated_and_is_not_approval(tmp_cfg, generated):
    section, model, save, agent = generated
    tmp_cfg.raw['review'] = {'design_revision': True}
    path = Generator(tmp_cfg, model, agent).run()[0]
    assert len(agent.calls) == 2
    assert 'Draft to check (untrusted, not evidence)' in agent.calls[1]
    assert 'cancelPending' in agent.calls[1]
    assert verify(model, section, path.read_text(encoding='utf-8'))['human_review'] == 'pending'
    original = path.read_bytes()
    good = agent.chat
    def bad_revision(system, user, **kw):
        result = good(system, user, **kw)
        return result.replace('cancelPending', 'inventedFunction') if kw['tag'].endswith('_revision') else result
    agent.chat = bad_revision
    with pytest.raises(ValueError, match='실제 원문'):
        Generator(tmp_cfg, model, agent).run()
    assert path.read_bytes() == original


def test_passages_keep_context_and_reject_forged_source():
    from sdd.generated_design import source_passages, resolve_passages, quote_text
    source = 'if (!ready) {\n  return;\n}\n\n* Continue processing.\n*\nfinish();'
    annotated, passages = source_passages({'code': source})
    assert quote_text('\n\n'.join(item['text'] for item in annotated['code'])) == quote_text(source)
    code = 'result = value\n    * scale;'
    preserved, code_passages = source_passages({'expression': code})
    assert preserved['expression'][0]['text'] == code
    assert code_passages['expression:0'] == ('expression', code)
    key = next(iter(passages))
    with pytest.raises(ValueError, match='제공된 소스 ID'):
        resolve_passages([dict(quote_id=key, text='설명합니다.', covers=['q'], kind='behavior', evidence=['forged'])], passages)


def test_changed_source_regenerates_and_selects_overview_without_watch(tmp_cfg, generated):
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    before = fingerprint(model, section)
    model.meta['source_commit'] = 'b' * 40
    record = model.evidence['device/stop/stop']
    record.update(commit='b' * 40, text='void stop() { drain(); }')
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    save()
    report = compute(tmp_cfg, model, ['device.cpp'], 'a' * 40, 'b' * 40, non_semantic={})
    assert 'device' in report.sections
    assert not carry_forward(tmp_cfg, model, [])[0]
    agent.statement['text'] = '`stop()`은 종료 시 대기 중인 작업을 마치는 함수를 호출합니다. 구현자는 이 종료 진입점에서 작업 마무리 처리가 시작된다는 점을 확인하고 해당 처리 함수의 구현을 함께 읽어야 합니다.'
    agent.statement['quote'] = record['text']
    Generator(tmp_cfg, model, agent).run(impact=report)
    assert before != fingerprint(model, section)
    assert 'drain' in agent.calls[-1] and 'cancelPending' not in agent.calls[-1]
    assert verify(model, section, path.read_text(encoding='utf-8'))['status'] == 'documented'


@pytest.mark.parametrize('change', ['dry-run', 'budget', 'duplicate_mapping', 'stale_evidence'])
def test_fail_closed_before_model_or_manuscript(tmp_cfg, generated, change):
    section, model, save, agent = generated
    if change == 'dry-run': tmp_cfg.agent.kind = 'dry-run'
    if change == 'budget': tmp_cfg.agent.max_input_chars = 1
    if change == 'duplicate_mapping': section['design_topics'][0]['covers'].append('shutdown')
    if change == 'stale_evidence': model.evidence['device/stop/stop']['commit'] = 'b' * 40
    save()
    with pytest.raises(ValueError): Generator(tmp_cfg, model, agent).run()
    assert not agent.calls
    assert not (tmp_cfg.sdd_dir / 'device.md').exists()


@pytest.mark.parametrize('kind', ['ollama', 'openai-compatible'])
def test_structured_transport_preserves_generic_gateway_compatibility(tmp_cfg, monkeypatch, kind):
    from sdd.llm import Agent
    from sdd.generated_design import response_schema
    tmp_cfg.agent.kind = kind
    agent = Agent(tmp_cfg.agent)
    schema = response_schema({'sources': [{'id': 'source'}], 'covers': ['question']})
    calls = []
    def post(url, body):
        calls.append(body)
        return {'message': {'content': '{}'}, 'choices': [{'message': {'content': '{}'}}]}
    monkeypatch.setattr(agent, '_post', post)
    agent.chat('system', 'user', response_schema=schema)
    assert (calls[0].get('format') == schema) == (kind == 'ollama')
    assert 'response_format' not in calls[0]


def test_code_typography_uses_source_identifiers_without_rewriting_claims():
    from sdd.facts.model import ClassInfo
    from sdd.generated_design import normalize_answer
    model = KnowledgeModel(classes={name: ClassInfo(name=name) for name in ['Camera', 'Device', 'DeviceEnumerator']})
    statements = [{'text': 'Camera::start()와 `Camera`를 확인합니다. Device Enumerator는 장치를 찾습니다.'}]
    normalize_answer(model, statements, ['class Camera {}; class DeviceEnumerator {};'])
    assert statements[0]['text'] == '`Camera::start()`와 `Camera`를 확인합니다. Device Enumerator는 장치를 찾습니다.'


def test_quote_comparison_ignores_comment_decoration_but_preserves_negation():
    from sdd.generated_design import quote_text
    source = 'It must not access\n * the request after completion.'
    assert quote_text(source) == quote_text('It must not access the request after completion.')
    assert quote_text('It must access the request after completion.') not in quote_text(source)




@pytest.mark.parametrize('setting', ['project', 'section'])
def test_grounding_rejection_retries_the_model_without_replacing_prose(tmp_cfg, generated, setting):
    section, model, save, base = generated
    tmp_cfg.raw.setdefault('review', {})['design_grounding'] = setting == 'project'
    if setting == 'section':
        section['design_grounding'] = True
        save()
    class Agent:
        calls = []
        checks = 0
        def chat(self, system, user, **kwargs):
            self.calls.append((kwargs['tag'], user))
            if kwargs['tag'].endswith('_grounding'):
                self.checks += 1
                return json.dumps({'reviews': [dict(index=0, supported=self.checks > 1,
                                                    reason='Unsupported guarantee in the first draft')]})
            return json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    agent = Agent()
    path = Generator(tmp_cfg, model, agent).run()[0]
    assert len(agent.calls) == 4
    assert 'Unsupported guarantee' in agent.calls[2][1]
    assert 'cancelPending' in agent.calls[1][1]
    assert verify(model, section, path.read_text(encoding='utf-8'))['human_review'] == 'pending'


def test_enabling_grounding_invalidates_unguarded_topic_reuse(tmp_cfg, generated):
    from sdd.impact import ImpactReport
    section, model, save, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    before = path.read_bytes()
    agent.calls.clear()
    tmp_cfg.raw.setdefault('review', {})['design_grounding'] = True
    with pytest.raises(ValueError, match='근거 대조'):
        Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='b'*40, sections=['device']))
    assert agent.calls and path.read_bytes() == before


@pytest.mark.parametrize('reason', ['', 'x' * 401])
def test_grounding_requires_bounded_verdict_reasons(tmp_cfg, reason):
    from types import SimpleNamespace
    from sdd.grounding import review
    class Agent:
        def chat(self, *args, **kwargs):
            return json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': reason}]})
    with pytest.raises(ValueError, match='근거 대조 응답'):
        review(SimpleNamespace(cfg=tmp_cfg, agent=Agent()), {'question': 'What happens?'},
               [{'text': 'A claim', 'quote': 'Source statement', 'evidence': ['s']}],
               {'s': 'Source statement'}, 'bounded')


def test_json_code_string_literals_survive_without_schema_character_class(tmp_cfg, generated):
    from sdd.generated_design import response_schema
    section, model, save, agent = generated
    field = response_schema(section['design_topics'][0])['properties']['statements']['items']['properties']['text']
    assert field == {'type': 'string', 'maxLength': 600}
    agent.statement['text'] += ' 코드 문자열의 표기는 `"diagnostic"`입니다.'
    path = Generator(tmp_cfg, model, agent).run()[0]
    assert '`"diagnostic"`' in path.read_text(encoding='utf-8')
    agent.statement['text'] += '\n별도 문단입니다.'
    with pytest.raises(ValueError, match='한 문단'):
        Generator(tmp_cfg, model, agent).run()


def test_investigation_receives_actual_source_paths_and_scope(tmp_cfg, generated):
    section, model, save, base = generated
    section['design_topics'][0]['answer_contract'] = {'basis': 'investigation'}
    save()
    class Agent:
        def chat(self, system, user, **kwargs):
            assert 'source-based debugging plan' in system
            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
            assert payload['source_files'] == {'stop': 'device.cpp'}
            return json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    assert Generator(tmp_cfg, model, Agent()).run()


def test_changed_grounding_policy_requires_new_review(tmp_cfg, generated, monkeypatch):
    from sdd.impact import ImpactReport
    section, model, save, base = generated
    tmp_cfg.raw.setdefault('review', {})['design_grounding'] = True
    class Agent:
        calls = 0
        def chat(self, system, user, **kwargs):
            self.calls += 1
            if kwargs['tag'].endswith('_grounding'):
                return json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': 'Source matches.'}]})
            return json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    agent = Agent()
    path = Generator(tmp_cfg, model, agent).run()[0]
    old = path.read_text(encoding='utf-8')
    monkeypatch.setattr('sdd.grounding.policy_hash', lambda: 'new-policy')
    with pytest.raises(ValueError, match='政策|정책'):
        verify(model, section, old)
    Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='a'*40, sections=['device']))
    assert agent.calls == 4
    assert verify(model, section, path.read_text(encoding='utf-8'))['human_review'] == 'pending'


def test_quote_anchor_can_have_additional_real_source_evidence():
    from sdd.generated_design import resolve_passages
    passages = {'a:0': ('a', 'A real source passage.'), 'b:0': ('b', 'Another real passage.')}
    row = dict(text='두 입력을 설명합니다.', quote_id='a:0', evidence=['a', 'b'], covers=['flow'], kind='behavior')
    resolved = resolve_passages([row], passages)[0]
    assert resolved['quote'] == 'A real source passage.' and resolved['evidence'] == ['a', 'b']
    for invalid in (['b'], ['a', 'invented'], ['a', 'a']):
        with pytest.raises(ValueError, match='제공된 소스 ID'):
            resolve_passages([{**row, 'evidence': invalid}], passages)


def test_parts_preserve_focus_source_before_supporting_context(tmp_cfg, generated):
    section, model, save, base = generated
    topic = section['design_topics'][0]
    extra = dict(id='context', file='context.cpp', start='void context()', end='}')
    text = 'void context() { inspect(); }'
    topic['sources'].append(extra)
    model.evidence['device/stop/context'] = dict(selector=extra, commit='a'*40, file='context.cpp',
        line=1, end_line=1, text=text, sha256=hashlib.sha256(text.encode()).hexdigest(), status='available')
    topic['parts'] = [dict(id='focus', question='종료 호출을 설명하세요.', sources=['context', 'stop'])]
    save()
    class Agent:
        def chat(self, system, user, **kwargs):
            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{'):])
            assert list(payload['sources']) == ['context', 'stop']
            return json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    assert Generator(tmp_cfg, model, Agent()).run()





def test_libcamera_design_documents_have_no_fixed_answers():
    from pathlib import Path
    from sdd.contract_schema import configuration_errors
    sections = yaml.safe_load((Path(__file__).parents[1] / 'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))['sections']
    designs = [section for section in sections if section.get('design_requirements')]
    assert len(designs) == 19
    # #164 moves duplicate overview queue limits to the existing request detail.
    assert sum(len(section['design_topics']) for section in designs) == 68
    by_id = {section['id']: section for section in designs}
    for page in ('vendor-overview', 'overview'):
        assert 'queue-limit' not in {t['id'] for t in by_id[page]['design_topics']}
        assert any(d['location'].startswith('pipeline-requests.md#')
                   for d in by_id[page]['reader_scope']['optional'])
    assert 'queue-limit' in {t['id'] for t in by_id['pipeline-requests']['design_topics']}
    for section in designs:
        assert section['design_generation'] == 'llm'
        assert not configuration_errors(section)
        assert all('statements' not in topic for topic in section['design_topics'])
        assert all('sha256' not in source for topic in section['design_topics'] for source in topic['sources'])


@pytest.mark.parametrize('profile', ['architecture', 'vendor', 'vendor-overview', 'vendor-assurance'])
def test_reader_profile_validates_full_coverage_and_retries_dense_topic(tmp_cfg, generated, profile):
    from sdd.reader_profiles import PROFILES
    section, model, save, base_agent = generated
    section['reader_profile'] = profile
    template = section['design_topics'][0]
    section['design_topics'] = []
    section['design_requirements'] = []
    for number, (aspect, question) in enumerate(PROFILES[profile].items()):
        section['design_topics'].append({**copy.deepcopy(template), 'id': aspect, 'covers': [aspect]})
        section['design_requirements'].append(dict(id=aspect, question=question, aspects=[aspect]))
        # 주제마다 다른 발췌를 근거로 삼아야 같은 근거의 중복 설명으로 반려되지 않는다.
        record = copy.deepcopy(model.evidence['device/stop/stop'])
        record['text'] = record['text'] + f' /* {aspect} */'
        record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
        record['line'] = record['end_line'] = 100 * (number + 1)
        model.evidence[f'device/{aspect}/stop'] = record
    save()

    class ProfileAgent:
        calls = []
        def chat(self, system, user, **kw):
            if profile == 'vendor-overview':
                assert 'source-backed benefits' in system
                assert 'performance numbers' in system
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            statement_schema = kw['response_schema']['properties']['statements']['items']
            statement['covers'] = statement_schema['properties']['covers']['items']['enum']
            statement['quote'] = statement['quote'] + f' /* {statement["covers"][0]} */'
            if len(self.calls) == 1:
                statement['text'] = '요청을 취소합니다. ' * 80
            return json.dumps({'statements': [statement]}, ensure_ascii=False)

    agent = ProfileAgent()
    path = Generator(tmp_cfg, model, agent).run()[0]
    assert len(agent.calls) == len(PROFILES[profile]) + 1
    assert '600자' in agent.calls[1]
    assert verify(model, section, path.read_text(encoding='utf-8'))['status'] == 'documented'
    export_site(tmp_cfg)
    original = path.read_bytes()
    section['design_requirements'][0]['aspects'] = []
    save()
    agent.calls.clear()
    with pytest.raises(ValueError, match='필수 독자 질문'):
        Generator(tmp_cfg, model, agent).run()
    assert not agent.calls and path.read_bytes() == original


def test_full_trial_collects_independent_unit_failures_without_replacing_page(tmp_cfg, generated):
    section, model, save, agent = generated
    page = Generator(tmp_cfg, model, agent).run()[0]
    before = page.read_bytes()
    section['design_topics'][0]['parts'] = [
        {'id': 'first', 'question': '첫 책임을 설명하세요.', 'sources': ['stop']},
        {'id': 'second', 'question': '두 번째 책임을 설명하세요.', 'sources': ['stop']}]
    save()
    class Empty:
        def __init__(self): self.tags = []
        def chat(self, system, user, **kwargs):
            self.tags.append(kwargs['tag'])
            return '{"statements": []}'
    empty = Empty()
    with pytest.raises(ValueError) as error:
        Generator(tmp_cfg, model, empty, all_design_units=True).run()
    assert 'device/stop/first' in str(error.value) and 'device/stop/second' in str(error.value)
    assert any('first' in tag for tag in empty.tags) and any('second' in tag for tag in empty.tags)
    assert page.read_bytes() == before
    default = Empty()
    with pytest.raises(ValueError):
        Generator(tmp_cfg, model, default).run()
    assert all('first' in tag for tag in default.tags)


def test_unrendered_source_documentation_command_is_rejected(tmp_cfg, generated):
    _, model, _, agent = generated
    agent.statement['text'] = r'`stop()`은 대기 요청을 취소하며 \ref camera_operation 설명을 따릅니다.'
    with pytest.raises(ValueError, match='Doxygen'):
        Generator(tmp_cfg, model, agent).run()


@pytest.mark.parametrize('tamper', [False, True])
def test_grounding_uses_verified_full_scope_without_inventing_context(tmp_cfg, tamper):
    from types import SimpleNamespace
    from sdd.grounding import review
    selected = 'return result;'
    surrounding = 'void Owner::method() { if (ready) { return result; } }'
    record = {'context': {'text': surrounding, 'sha256': hashlib.sha256(surrounding.encode()).hexdigest()}}
    class Agent:
        def chat(self, system, user, **kwargs):
            assert json.loads(user)['source_context']['s'] == surrounding
            return json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': 'Bounded source method.'}]})
    if tamper:
        record['context']['text'] = 'Different scope'
    args = (SimpleNamespace(cfg=tmp_cfg, agent=Agent()), {'question': 'What does this method do?'},
            [{'text': 'A statement', 'quote': selected, 'evidence': ['s']}], {'s': selected}, 'scoped')
    options = {'source_scopes': {'s': {'start': 'void Owner::method()', 'end': '}'}}, 'context_records': {'s': record}}
    if tamper:
        with pytest.raises(ValueError, match='전체 원문'):
            review(*args, **options)
    else:
        review(*args, **options)
def test_source_backed_cpp_template_typography_preserves_model_words():
    from sdd.generated_design import normalize_answer
    from sdd.facts.model import KnowledgeModel
    text = 'std::vector<double> 값을 반환합니다. <script>와 std::evil<script>는 근거에 없습니다.'
    answers = [{'text': text}]
    normalize_answer(KnowledgeModel(), answers, ['std::vector<double> positions;'])
    assert answers[0]['text'] == '`std::vector<double>` 값을 반환합니다. <script>와 std::evil<script>는 근거에 없습니다.'
    assert answers[0]['text'].replace('`', '') == text
    once = answers[0]['text']
    normalize_answer(KnowledgeModel(), answers, ['std::vector<double> positions;'])
    assert answers[0]['text'] == once


def test_unqualified_source_template_is_code_not_html():
    from sdd.generated_design import normalize_answer
    from sdd.facts.model import KnowledgeModel
    answers = [{'text': 'Matrix<double, 3, 3> 행렬을 읽습니다.'}]
    normalize_answer(KnowledgeModel(), answers, ['Matrix<double, 3, 3> cm;'])
    assert answers[0]['text'] == '`Matrix<double, 3, 3>` 행렬을 읽습니다.'


def test_topic_prompt_override_is_used_and_invalidates_its_answers(tmp_cfg, generated):
    from sdd.impact import ImpactReport
    section, model, save, agent = generated
    tmp_cfg.raw['review'] = {'design_prompt': 'standard'}
    (tmp_cfg.prompts_dir / 'focused-design-system.md').write_text('근거만 설명하세요.', encoding='utf-8')
    topic = section['design_topics'][0]
    topic['design_prompt'] = 'focused'
    save()
    Generator(tmp_cfg, model, agent).run()
    assert agent.calls[0].startswith('근거:')
    topic['design_prompt'] = 'standard'
    save()
    agent.calls.clear()
    Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='a'*40, sections=['device']))
    assert len(agent.calls) == 1 and not agent.calls[0].startswith('근거:')


def test_part_typography_matches_other_verified_sources_in_same_topic(tmp_cfg, generated):
    from sdd.generated_design import decode_unit
    from sdd.facts.model import ClassInfo
    section, model, save, agent = generated
    model.classes['ns::Fence'] = ClassInfo('ns::Fence')
    model.evidence['device/stop/other'] = {'status': 'available', 'text': 'class Fence;'}
    unit = section['design_topics'][0]
    statement = copy.deepcopy(agent.statement)
    statement['text'] = 'Fence 사용 시 stop()은 종료 요청을 취소하는 함수를 호출합니다.'
    raw = json.dumps({'statements': [statement]}, ensure_ascii=False)
    source = model.evidence['device/stop/stop']['text']
    answer = decode_unit(model, section, unit, raw, {'stop': source}, {})[0]
    assert answer['text'] == '`Fence` 사용 시 stop()은 종료 요청을 취소하는 함수를 호출합니다.'
    assert answer['text'].replace('`', '') == statement['text']


def test_focused_investigation_prompt_allows_proposals_without_claiming_execution(tmp_cfg, generated):
    section, model, save, agent = generated
    topic = section['design_topics'][0]
    topic['design_prompt'] = 'focused'
    topic['answer_contract'] = {'basis': 'investigation'}
    (tmp_cfg.prompts_dir/'focused-design-system.md').write_text('제공된 소스만 사용합니다.', encoding='utf-8')
    save()
    class PlanAgent:
        def chat(self, system, user, **kwargs):
            assert 'optional source-based observation plan' in system
            assert 'not an existing test log' in system
            return json.dumps({'statements': [agent.statement]}, ensure_ascii=False)
    assert Generator(tmp_cfg, model, PlanAgent()).run()


@pytest.mark.parametrize('selection', ['runner', 'model', 'args', 'default'])
def test_cli_selection_invalidates_topic_reuse(tmp_cfg, generated, selection):
    from sdd.impact import ImpactReport
    section, model, save, agent = generated
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.runner = 'hermes'
    tmp_cfg.agent.model = 'approved-model' if selection != 'default' else ''
    Generator(tmp_cfg, model, agent).run()
    agent.calls.clear()
    if selection == 'runner':
        tmp_cfg.agent.runner = 'claude'
    elif selection == 'model':
        tmp_cfg.agent.model = 'other-model'
    elif selection == 'args':
        tmp_cfg.agent.args = ['--provider', 'other']
    Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='b'*40, sections=['device']))
    assert len(agent.calls) == 1


def test_A1_같은_근거를_되풀이한_답변은_재요청_사유와_함께_반려한다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='first', question='종료 시 호출 함수는 무엇입니까?', sources=['stop']),
                      dict(id='second', question='종료 진입점에서 확인할 책임은 무엇입니까?', sources=['stop'])]
    save()
    distinct = '`stop()`의 본문에는 `cancelPending()`을 호출하는 문장 한 줄만 있습니다.'

    class Agent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            if len(self.calls) == 3:
                statement['text'] = distinct
            return json.dumps({'statements': [statement]}, ensure_ascii=False)

    agent = Agent()
    path = Generator(tmp_cfg, model, agent).run()[0]
    assert len(agent.calls) == 3
    assert '[의미 중복]' in agent.calls[2] and '[의미 중복]' not in agent.calls[1]
    body = path.read_text(encoding='utf-8').split('\n---\n', 1)[1]
    assert body.count('종료 시 대기 중인 요청을 취소하는 함수를 호출합니다') == 1 and distinct in body


def test_A1_다시_써도_되풀이하면_생성을_실패시키고_기존_원고를_보존한다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='first', question='종료 시 호출 함수는 무엇입니까?', sources=['stop']),
                      dict(id='second', question='종료 진입점에서 확인할 책임은 무엇입니까?', sources=['stop'])]
    save()
    with pytest.raises(ValueError, match='의미 중복'):
        Generator(tmp_cfg, model, base_agent).run()
    assert not (tmp_cfg.sdd_dir / 'device.md').exists()


def test_source_member_underscores_render_verbatim_without_rewriting_model_text(tmp_cfg, generated):
    from sdd.generated_design import normalize_answer
    _, model, _, _ = generated
    statement = {'text': '조사에서 _d()->metadata_ 변수를 기록 항목으로 제안합니다.'}
    original = statement['text']
    normalize_answer(model, [statement], ['_d()->metadata_.clear();'])
    assert statement['text'].replace('`', '') == original
    import html, re, markdown
    rendered = markdown.markdown(statement['text'])
    assert '_d()->metadata_' in html.unescape(re.sub('<[^>]+>', '', rendered))
    assert '<em>' not in rendered


def test_new_typography_keeps_source_identical_saved_answers(tmp_cfg, generated):
    from sdd.impact import ImpactReport
    import sdd.generated_design as design
    section, model, save, agent = generated
    agent.statement['text'] = 'stop()은 status_ 값을 확인합니다.'
    model.evidence['device/stop/stop']['text'] += '\nint status_ = 0;'
    model.evidence['device/stop/stop']['sha256'] = design.digest(model.evidence['device/stop/stop']['text'])
    save()
    from unittest.mock import patch
    # Create a valid legacy manuscript under its original typography rules.
    with patch.object(design, 'normalize_answer'), patch.object(design, 'source_names', return_value=set()):
        Generator(tmp_cfg, model, agent).run()
    agent.calls.clear()
    paths = Generator(tmp_cfg, model, agent).run(impact=ImpactReport(base='a'*40, head='b'*40, sections=['device']))
    assert not agent.calls
    assert '`status_`' in paths[0].read_text(encoding='utf-8')


def test_B5_statement_kind를_지정한_질문은_모델이_고르지_않고_실행_확인_항목으로_고정된다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='what', question='종료 진입점은 무엇을 호출합니까?', sources=['stop']),
                      dict(id='try', question='종료 동작을 직접 확인하려면 무엇을 실행합니까?', sources=['stop'],
                           statement_kind='limitation')]
    save()
    from sdd.generated_design import response_schema
    assert response_schema({**topic, '_statement_kind': 'limitation'})['properties']['statements']['items'][
        'properties']['kind']['enum'] == ['limitation']

    class Agent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            if len(self.calls) == 2:
                assert kw['response_schema']['properties']['statements']['items']['properties']['kind']['enum'] == ['limitation']
                statement['text'] = '`stop()`을 호출한 뒤 `cancelPending()`이 대기 요청을 취소하는지 로그로 확인합니다.'
                statement['kind'] = 'behavior'  # 모델이 잘못 고른 경우에도 생성기가 고정한다
            return json.dumps({'statements': [statement]}, ensure_ascii=False)

    path = Generator(tmp_cfg, model, Agent()).run()[0]
    body = path.read_text(encoding='utf-8').split('\n---\n', 1)[1]
    assert '실행 확인 항목: `stop()`을 호출한 뒤' in body
    assert '실행 확인 항목: `stop()`은 종료 시' not in body


def test_B5_statement_kind는_limitation만_허용하고_답변_계약과_함께_쓸_수_없다(tmp_cfg, generated):
    section, model, save, agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='x', question='실행 방법은 무엇입니까?', sources=['stop'], statement_kind='behavior')]
    save()
    with pytest.raises(ValueError, match='statement_kind'):
        Generator(tmp_cfg, model, agent).run()
    topic['parts'] = [dict(id='x', question='실행 방법은 무엇입니까?', sources=['stop'], statement_kind='limitation',
                           answer_contract=dict(basis='description'))]
    save()
    with pytest.raises(ValueError, match='statement_kind'):
        Generator(tmp_cfg, model, agent).run()



def test_B5_모든_parts가_limitation이면_모델을_부르기_전에_설정_오류로_막는다(tmp_cfg, generated):
    section, model, save, agent = generated
    section['design_topics'][0]['parts'] = [dict(id='x', question='실행 방법은 무엇입니까?', sources=['stop'], statement_kind='limitation')]
    save()
    with pytest.raises(ValueError, match='사실 답변이 없습니다'):
        Generator(tmp_cfg, model, agent).run()
    assert agent.calls == []


def test_게시_검증은_중복_문장을_경고로만_보고하고_생성은_계속_거부한다(tmp_cfg, generated):
    from sdd.generated_design import validate_answers
    section, model, save, agent = generated
    first = agent.statement
    second = {**first, 'text': first['text'].replace('은 종료 시', '은 정지할 때')}
    answers = {'stop': [first, second]}
    with pytest.raises(ValueError, match='의미 중복'):
        validate_answers(model, section, answers)
    _, _, report = validate_answers(model, section, answers, enforce_repeats=False)
    assert report['status'] == 'documented'


def _summary_agent(base_agent, summary_text):
    class Agent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            if len(self.calls) == 1:
                statement['text'] = summary_text
            return json.dumps({'statements': [statement]}, ensure_ascii=False)
    return Agent()


SUMMARY_TEXT = '`stop()`은 종료 시 대기 중인 요청을 취소하는 함수를 호출합니다.'


def test_주제_요약은_첫_문단으로_따로_쓰고_뒤_설명의_중복_비교_대상에서_빠진다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='core', role='summary', question='종료에서 먼저 알아야 할 결론은 무엇입니까?', sources=['stop']),
                      dict(id='detail', question='종료 진입점은 무엇을 호출합니까?', sources=['stop'])]
    save()
    agent = _summary_agent(base_agent, SUMMARY_TEXT)
    path = Generator(tmp_cfg, model, agent).run()[0]
    for instruction in ('opening summary', 'one or two short, plain Korean sentences',
                        'conclusion or key distinction', 'Describe what happens before naming code',
                        'Keep the conditions and may/must/negation', 'add nothing the sources do not state'):
        assert instruction in agent.calls[0]
    assert 'opening summary' not in agent.calls[1]
    body = path.read_text(encoding='utf-8').split('\n---\n', 1)[1]
    detail = base_agent.statement['text']
    # 요약은 상세 설명과 같은 문단에 합치지 않고 앞에 둔다.
    assert f'{SUMMARY_TEXT} `device.cpp:10`\n\n{detail} `device.cpp:10`' in body
    assert verify(model, section, path.read_text(encoding='utf-8'))['human_review'] == 'pending'


def test_요약_역할이_없으면_같은_내용의_뒤_설명은_중복으로_거절된다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    topic = section['design_topics'][0]
    topic['parts'] = [dict(id='core', question='종료에서 먼저 알아야 할 결론은 무엇입니까?', sources=['stop']),
                      dict(id='detail', question='종료 진입점은 무엇을 호출합니까?', sources=['stop'])]
    save()
    with pytest.raises(ValueError, match='의미 중복'):
        Generator(tmp_cfg, model, _summary_agent(base_agent, SUMMARY_TEXT)).run()


@pytest.mark.parametrize('parts', [
    [dict(id='detail', question='무엇을 호출합니까?', sources=['stop']),
     dict(id='core', role='summary', question='결론은 무엇입니까?', sources=['stop'])],
    [dict(id='core', role='summary', question='결론은 무엇입니까?', sources=['stop'])],
    [dict(id='core', role='intro', question='결론은 무엇입니까?', sources=['stop']),
     dict(id='detail', question='무엇을 호출합니까?', sources=['stop'])],
    [dict(id='core', role='summary', max_statements=3, question='결론은 무엇입니까?', sources=['stop']),
     dict(id='detail', question='무엇을 호출합니까?', sources=['stop'])],
])
def test_요약_part는_상세_part_앞의_첫_part에만_둘_수_있다(tmp_cfg, generated, parts):
    section, model, save, agent = generated
    section['design_topics'][0]['parts'] = parts
    save()
    with pytest.raises(ValueError, match='role: summary'):
        Generator(tmp_cfg, model, agent).run()
    assert not agent.calls


def test_다른_주제가_앞_주제의_요약을_되풀이하면_중복으로_거절된다(tmp_cfg, generated):
    section, model, save, base_agent = generated
    first = section['design_topics'][0]
    first['parts'] = [dict(id='core', role='summary', question='종료에서 먼저 알아야 할 결론은 무엇입니까?', sources=['stop']),
                      dict(id='detail', question='종료 진입점은 무엇을 호출합니까?', sources=['stop'])]
    section['design_requirements'].append(dict(id='again', question='종료 진입점을 다시 설명합니까?'))
    section['design_topics'].append(dict(id='again', title='다시 쓰는 종료', question='종료를 설명하세요.',
                                         covers=['again'], sources=copy.deepcopy(first['sources'])))
    model.evidence['device/again/stop'] = copy.deepcopy(model.evidence['device/stop/stop'])
    save()

    class Agent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            if len(self.calls) == 1:
                statement['text'] = SUMMARY_TEXT
            elif len(self.calls) == 2:
                # 앞 주제의 상세 설명은 요약과 겹치지 않게 두어, 뒤 주제가 요약 자체와만 겹치게 한다.
                statement['text'] = '구현자는 `cancelPending()`의 정의를 같은 파일에서 이어서 읽어야 합니다.'
            else:
                statement.update(text=SUMMARY_TEXT, covers=['again'])
            return json.dumps({'statements': [statement]}, ensure_ascii=False)

    with pytest.raises(ValueError, match='의미 중복'):
        Generator(tmp_cfg, model, Agent()).run()


def test_요약_답변은_실행_확인_항목으로_표시되지_않고_사실_문단으로_고정된다(tmp_cfg, generated):
    from sdd.generated_design import response_schema
    from sdd.design_request import _design_units
    section, model, save, base_agent = generated
    section['design_topics'][0]['parts'] = [
        dict(id='core', role='summary', question='종료에서 먼저 알아야 할 결론은 무엇입니까?', sources=['stop']),
        dict(id='detail', question='종료 진입점은 무엇을 호출합니까?', sources=['stop'])]
    save()
    summary_unit = _design_units(section, {})[0]
    assert response_schema(summary_unit)['properties']['statements']['items']['properties']['kind']['enum'] == ['behavior']

    class Agent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            if len(self.calls) == 1:
                statement.update(text=SUMMARY_TEXT, kind='limitation')  # 모델이 잘못 골라도 생성기가 고정한다
            return json.dumps({'statements': [statement]}, ensure_ascii=False)

    body = Generator(tmp_cfg, model, Agent()).run()[0].read_text(encoding='utf-8').split('\n---\n', 1)[1]
    assert f'{SUMMARY_TEXT} `device.cpp:10`\n\n' in body
    assert '실행 확인 항목: ' + SUMMARY_TEXT not in body


def test_CLI_실행_파일_위치만_바뀌면_설계_재사용_신원이_유지된다(tmp_cfg, generated):
    from sdd.design_request import prepare_requests
    section, model, _, _ = generated
    tmp_cfg.agent.kind, tmp_cfg.agent.runner, tmp_cfg.agent.model = 'cli', 'codex', 'test-model'
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\0ab0e7a8\codex.EXE']
    before = prepare_requests(tmp_cfg, model, section, None).inputs
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\22cfb1d3\codex.exe']
    assert prepare_requests(tmp_cfg, model, section, None).inputs == before
    tmp_cfg.agent.command = [r'C:\Apps\Codex\bin\22cfb1d3\codex.exe', '--profile', 'other']
    assert prepare_requests(tmp_cfg, model, section, None).inputs != before
