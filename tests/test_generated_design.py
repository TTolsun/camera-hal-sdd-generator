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
            return json.dumps({'statements': [self.statement]}, ensure_ascii=False)
    return section, model, save, Agent()


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


def test_no_quotable_excerpt_fails_before_model_call(tmp_cfg, generated):
    section, model, save, agent = generated
    record = model.evidence['device/stop/stop']
    record['text'] = 'x' * 1700
    record['sha256'] = hashlib.sha256(record['text'].encode()).hexdigest()
    save()
    with pytest.raises(ValueError, match='인용 구절이 없습니다'):
        Generator(tmp_cfg, model, agent).run()
    assert not agent.calls


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


def test_constrained_quote_choices_are_verbatim_source_spans():
    from sdd.generated_design import quote_choices, quote_text, response_schema
    source = 'The handler shall not access\n * the request after completion.\n *\n * Return requests in order.'
    choices = quote_choices([source])
    assert 'The handler shall not access the request after completion.' in choices
    assert 'The handler shall not access' not in choices
    assert all(quote in quote_text(source) for quote in choices)
    schema = response_schema({'sources': [{'id': 'source'}], 'covers': ['question']}, choices)
    assert schema['properties']['statements']['items']['properties']['quote']['enum'] == choices


def test_quote_schema_binds_each_excerpt_to_its_source_id():
    from sdd.generated_design import response_schema
    topic = {'sources': [{'id': 'queue'}, {'id': 'complete'}], 'covers': ['lifecycle']}
    quotes = {'queue': ['Queue the request.'], 'complete': ['Complete the request.']}
    schema = response_schema(topic, [q for values in quotes.values() for q in values], quotes)
    choices = schema['properties']['statements']['items']['anyOf']
    for choice, (source, spans) in zip(choices, quotes.items()):
        assert choice['required'] == ['quote', 'text', 'evidence', 'covers', 'kind']
        assert choice['properties']['quote']['enum'] == spans
        assert choice['properties']['evidence']['const'] == [source]
        assert choice['properties']['covers']['items']['enum'] == ['lifecycle']
        assert 'text' in choice['properties'] and 'kind' in choice['properties']


def test_libcamera_design_documents_have_no_fixed_answers():
    from pathlib import Path
    from sdd.contract_schema import configuration_errors
    sections = yaml.safe_load((Path(__file__).parents[1] / 'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))['sections']
    designs = [section for section in sections if section.get('design_requirements')]
    assert len(designs) == 8
    for section in designs:
        assert section['design_generation'] == 'llm'
        assert not configuration_errors(section)
        assert all('statements' not in topic for topic in section['design_topics'])
        assert all('sha256' not in source for topic in section['design_topics'] for source in topic['sources'])


@pytest.mark.parametrize('profile', ['architecture', 'vendor'])
def test_reader_profile_validates_full_coverage_and_retries_dense_topic(tmp_cfg, generated, profile):
    from sdd.reader_profiles import PROFILES
    section, model, save, base_agent = generated
    section['reader_profile'] = profile
    template = section['design_topics'][0]
    section['design_topics'] = []
    section['design_requirements'] = []
    for aspect, question in PROFILES[profile].items():
        section['design_topics'].append({**template, 'id': aspect, 'covers': [aspect]})
        section['design_requirements'].append(dict(id=aspect, question=question, aspects=[aspect]))
        model.evidence[f'device/{aspect}/stop'] = copy.deepcopy(model.evidence['device/stop/stop'])
    save()

    class ProfileAgent:
        calls = []
        def chat(self, system, user, **kw):
            self.calls.append(user)
            statement = copy.deepcopy(base_agent.statement)
            statement_schema = kw['response_schema']['properties']['statements']['items']['anyOf'][0]
            statement['covers'] = statement_schema['properties']['covers']['items']['enum']
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
