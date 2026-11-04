import copy
import hashlib
import json
import re

import pytest
import yaml

from sdd.document_metadata import split_frontmatter
from sdd.export_site import export_site
from sdd.generate import Generator
from sdd.generated_design import verify
from sdd.visual_refresh import refresh
from sdd.visuals import strip_blocks
from test_generated_design import cli_units, generated, scenario_prose


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def assembled(tmp_cfg, generated):
    section, model, _, agent = generated
    path = Generator(tmp_cfg, model, agent).run()[0]
    raw = path.read_bytes()
    ref = dict(source='stop/stop', sha256=model.evidence['device/stop/stop']['sha256'],
               quote='cancelPending();')
    graph = dict(id='stop-ownership', topic='stop', kind='ownership', title='취소 호출 관계',
                 question='종료 진입점은 어떤 취소 함수를 호출합니까?',
                 nodes=[dict(id='stop', label='종료 진입점', label_en='Stop entry', evidence=[ref]),
                        dict(id='cancel', label='취소 함수', label_en='Cancellation function', evidence=[ref])],
                 edges=[dict(**{'from': 'stop', 'to': 'cancel'}, label='취소 호출',
                             label_en='Calls cancellation', evidence=[ref])])
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    def save():
        (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(
            dict(schema=1, sections={'device': [graph]}), allow_unicode=True), encoding='utf-8')
    save()
    return section, model, agent, path, raw, graph, save


def test_reassembly_keeps_prose_and_origin_and_updates_download(tmp_cfg, assembled):
    section, model, agent, path, raw, _, _ = assembled
    count = len(agent.calls)
    result = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    before, original_body = split_frontmatter(raw.decode().replace('\r\n', '\n'))
    after, body = split_frontmatter(result.decode())
    assert strip_blocks(body).strip() == strip_blocks(original_body).strip()
    expected = copy.deepcopy(after)
    event = expected.pop('managed_visual_refresh')[0]
    expected['generated_design']['body_sha256'] = before['generated_design']['body_sha256']
    assert expected == before and len(agent.calls) == count
    assert event['added_visuals'] == ['stop-ownership']
    assert event['original_manuscript_sha256'] == digest(raw)
    assert event['new_inference'] is False and event['semantic_approval'] is False
    verify(model, section, result.decode(), cfg=tmp_cfg)
    assert path.read_bytes() == raw
    path.write_bytes(result)
    site = export_site(tmp_cfg)
    assert (site/'device.md').read_bytes() == result
    assert 'stop-ownership.mmd' in (site/'device.html').read_text(encoding='utf-8')
    assert refresh(tmp_cfg, model, 'device', result, expected_sha256=digest(result)) == result


@pytest.mark.parametrize('mutation', ['pin', 'source_commit', 'stale_omit', 'node_limit', 'question'])
def test_rejected_refresh_preserves_original_and_site(tmp_cfg, assembled, mutation):
    section, model, agent, path, raw, graph, save = assembled
    site = export_site(tmp_cfg)
    outputs = {p.relative_to(site).as_posix():p.read_bytes() for p in site.rglob('*') if p.is_file()}
    expected = digest(raw)
    if mutation == 'pin':
        expected = '0'*64
    elif mutation == 'source_commit':
        model.meta['source_commit'] = 'b'*40
    elif mutation == 'stale_omit':
        tmp_cfg.raw['visuals']['on_stale'] = 'omit'
        graph['nodes'][0]['evidence'][0]['sha256'] = '0'*64
        save()
    elif mutation == 'node_limit':
        tmp_cfg.raw['visuals']['max_nodes'] = 1
    else:
        section['design_topics'][0]['question'] = '변경된 독립 질문'
        tmp_cfg.sections_file.write_text(yaml.safe_dump(dict(sections=[section]), allow_unicode=True), encoding='utf-8')
    calls = len(agent.calls)
    with pytest.raises(ValueError):
        refresh(tmp_cfg, model, 'device', raw, expected_sha256=expected)
    assert path.read_bytes() == raw and len(agent.calls) == calls
    assert outputs == {p.relative_to(site).as_posix():p.read_bytes() for p in site.rglob('*') if p.is_file()}


def test_removing_owned_static_figure_is_not_an_automatic_refresh(tmp_cfg, assembled):
    _, model, _, _, raw, graph, save = assembled
    result = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    graph['id'] = 'replacement-id'
    save()
    with pytest.raises(ValueError, match='cannot delete'):
        refresh(tmp_cfg, model, 'device', result, expected_sha256=digest(result))


def test_noop_retains_original_crlf_bytes(tmp_cfg, assembled):
    _, model, _, _, raw, _, _ = assembled
    first = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    original_crlf = first.replace(b'\n', b'\r\n')
    assert refresh(tmp_cfg, model, 'device', original_crlf,
                   expected_sha256=digest(original_crlf)) == original_crlf


def test_changed_refresh_preserves_metadata_values_but_reserializes_yaml(tmp_cfg, assembled):
    _, model, _, path, raw, _, _ = assembled
    # The original remains the byte record. A derived artifact preserves parsed
    # metadata, not YAML comments or quoting; the lineage states its origin.
    fixture = raw.replace(b'---\n', b'---\n# historical comment\r\n', 1)
    fixture = fixture.replace(b'source_commit: '+b'a'*40,
                              b'source_commit: "'+b'a'*40+b'"')
    before, _ = split_frontmatter(fixture.decode().replace('\r\n', '\n'))
    result = refresh(tmp_cfg, model, 'device', fixture, expected_sha256=digest(fixture))
    after, _ = split_frontmatter(result.decode())
    event = after.pop('managed_visual_refresh')[0]
    after['generated_design']['body_sha256'] = before['generated_design']['body_sha256']
    assert after == before
    assert event['original_manuscript_sha256'] == digest(fixture)
    assert path.read_bytes() == raw and b'# historical comment\r\n' in fixture


def test_replacing_owned_figure_preserves_literal_surrounding_whitespace(tmp_cfg, assembled):
    _, model, _, path, raw, graph, save = assembled
    first = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    metadata, body = split_frontmatter(first.decode())
    closing = '<!-- /sdd:visual:stop-ownership -->'
    # Distinct mixed line endings, tabs and trailing spaces after the owned
    # marker expose the whitespace loss hidden by strip_blocks().strip().
    body = body.replace(closing, closing+'\r\n\t \r\n \t\n\r')
    view = body.replace('\r\n', '\n').replace('\r', '\n')
    metadata['generated_design']['body_sha256'] = digest(view.strip().encode())
    fixture = ('---\n'+yaml.safe_dump(metadata, allow_unicode=True)+'---\n'+body).encode()
    graph['title'] = '수정된 취소 호출 관계'
    save()
    result = refresh(tmp_cfg, model, 'device', fixture, expected_sha256=digest(fixture))
    # Independent byte-level projection: remove only marker-delimited spans,
    # never production stripping, newline normalization or surrounding spaces.
    def outside(value):
        content = value.split(b'\n---\n', 1)[1]
        return re.sub(rb'<!-- sdd:visual:stop-ownership -->.*?<!-- /sdd:visual:stop-ownership -->',
                      b'', content, flags=re.S)
    assert result != fixture and outside(result) == outside(fixture)
    assert b'\r\n\t \r\n \t\n\r' in outside(result)
    assert path.read_bytes() == raw


def test_addition_in_existing_topic_preserves_original_outside_bytes(tmp_cfg, assembled):
    _, model, _, _, raw, graph, _ = assembled
    first = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    added = copy.deepcopy(graph)
    added['id'] = 'second-stop'
    added['title'] = '추가 호출 관계'
    (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(
        dict(schema=1, sections={'device': [graph, added]}), allow_unicode=True), encoding='utf-8')
    result = refresh(tmp_cfg, model, 'device', first, expected_sha256=digest(first))
    def body(value):
        return value.split(b'\n---\n', 1)[1]
    before = re.sub(rb'<!-- sdd:visual:stop-ownership -->.*?<!-- /sdd:visual:stop-ownership -->',
                    b'', body(first), flags=re.S)
    after = re.sub(rb'<!-- sdd:visual:stop-ownership -->.*?<!-- /sdd:visual:second-stop -->',
                   b'', body(result), flags=re.S)
    assert before == after
    assert b'<!-- sdd:visual:second-stop -->' in result


def test_same_id_topic_move_requires_normal_generation(tmp_cfg, cli_units):
    section, model, _, calls, state, agent = cli_units
    state['interrupt'] = False
    path = Generator(tmp_cfg, model, agent()).run()[0]
    raw = path.read_bytes()
    ref = dict(source='stop/stop', sha256=model.evidence['device/stop/stop']['sha256'],
               quote='cancelPending();')
    graph = dict(id='stop-ownership', topic='stop', kind='ownership', title='Cancellation',
                 question='Which function receives cancellation?',
                 nodes=[dict(id='caller', label='Caller', label_en='Caller', evidence=[ref]),
                        dict(id='callee', label='Callee', label_en='Callee', evidence=[ref])],
                 edges=[dict(**{'from': 'caller', 'to': 'callee'}, label='Calls', label_en='Calls', evidence=[ref])])
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    def save():
        (tmp_cfg.root/'visuals.yaml').write_text(yaml.safe_dump(
            dict(schema=1, sections={'device': [graph]})), encoding='utf-8')
    save()
    first = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    # Both topics were authenticated during original generation; changing only
    # the authored figure topic must not leave it under the old explanation.
    graph['topic'] = 'prepare'
    save()
    count = len(calls)
    with pytest.raises(ValueError, match='another topic requires normal generation'):
        refresh(tmp_cfg, model, 'device', first, expected_sha256=digest(first))
    assert path.read_bytes() == raw and len(calls) == count


def test_owned_markers_inside_code_are_not_replaced(tmp_cfg, assembled):
    _, model, _, _, raw, _, _ = assembled
    metadata, body = split_frontmatter(raw.decode().replace('\r\n', '\n'))
    body += '\n```text\n<!-- sdd:visual:stop-ownership -->\nexample\n<!-- /sdd:visual:stop-ownership -->\n```\n'
    metadata['generated_design']['body_sha256'] = digest(body.strip().encode())
    fixture = ('---\n'+yaml.safe_dump(metadata, allow_unicode=True)+'---\n'+body).encode()
    with pytest.raises(ValueError, match='outside code fences'):
        refresh(tmp_cfg, model, 'device', fixture, expected_sha256=digest(fixture))


def test_historical_graph_records_are_verified_and_retained_without_calls(tmp_cfg, generated, monkeypatch):
    from dataclasses import asdict
    import subprocess
    from sdd.llm import Agent
    section, model, _, agent = generated
    plan = dict(id='native-stop', topic='stop', kind='flow', generation='llm',
                title='종료 호출', question='어떤 취소 함수를 호출합니까?')
    draft = dict(nodes=[dict(id='stop', symbol='stop', label='종료', label_en='Stop',
                            shape='box', quote_ids=['stop:0']),
                        dict(id='cancel', symbol='cancelPending', label='취소', label_en='Cancel',
                             shape='box', quote_ids=['stop:0'])],
                 edges=[dict(**{'from': 'stop', 'to': 'cancel'}, label='취소 호출',
                             label_en='Calls cancellation', condition_ref='always', quote_ids=['stop:0'])])
    # Synthetic completed CLI archives exercise profile/record preservation;
    # this fixture never launches a runner or calls a model/API.
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.runner = 'claude'
    tmp_cfg.agent.model = 'synthetic-historical-model'
    tmp_cfg.agent.args = ['--effort', 'high']
    tmp_cfg.agent.max_input_chars = 160000
    calls = []
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])
    def synthetic_run(argv, **kwargs):
        prompt = kwargs['prompt']
        calls.append(prompt)
        if 'Audit factual entailment' in prompt:
            answer = {'reviews': [dict(index=0, supported=True, reason='Synthetic matching source.')]}
        else:
            answer = draft if '"quote_ids"' in prompt else {'statements': [agent.statement]}
        return subprocess.CompletedProcess(argv, 0, json.dumps(dict(
            subtype='success', is_error=False, result=json.dumps(answer))), '')
    monkeypatch.setattr('sdd.cli_agent.run', synthetic_run)
    config = tmp_cfg.root/'visuals.yaml'
    tmp_cfg.raw['visuals'] = dict(file='visuals.yaml', max_nodes=4)
    config.write_text(yaml.safe_dump(dict(schema=1, sections={'device': [plan]}), allow_unicode=True), encoding='utf-8')
    path = Generator(tmp_cfg, model, Agent(tmp_cfg.agent, tmp_cfg.build_dir/'prompts')).run()[0]
    raw = path.read_bytes()
    before, _ = split_frontmatter(raw.decode().replace('\r\n', '\n'))
    ref = dict(source='stop/stop', sha256=model.evidence['device/stop/stop']['sha256'], quote='cancelPending();')
    added = dict(id='configured-stop', topic='stop', kind='ownership', title='별도 소유 관계',
                 question='어떤 함수에 처리를 위임합니까?',
                 nodes=[dict(id='caller', label='호출자', label_en='Caller', evidence=[ref]),
                        dict(id='callee', label='처리 함수', label_en='Callee', evidence=[ref])],
                 edges=[dict(**{'from': 'caller', 'to': 'callee'}, label='위임', label_en='Delegates', evidence=[ref])])
    config.write_text(yaml.safe_dump(dict(schema=1, sections={'device': [plan, added]}), allow_unicode=True), encoding='utf-8')
    historical_agent = asdict(tmp_cfg.agent)
    tmp_cfg.agent.model = 'different-current-model'
    with pytest.raises(ValueError, match='source or question changed'):
        refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    (tmp_cfg.root/'historical.yaml').write_text(yaml.safe_dump(dict(
        agent=historical_agent, paths=dict(style=str(tmp_cfg.style_dir)))), encoding='utf-8')
    tmp_cfg.raw['site'] = dict(manuscript_profiles={'device.md': 'historical.yaml'})
    count = len(calls)
    result = refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))
    after, _ = split_frontmatter(result.decode())
    assert after['generated_visuals']['records'] == before['generated_visuals']['records']
    assert after['generated_design']['answers'] == before['generated_design']['answers']
    assert after['agent'] == before['agent'] and len(calls) == count
    assert path.read_bytes() == raw and tmp_cfg.agent.model == 'different-current-model'
    # A same-ID authored replacement must not retain an unverified LLM record.
    converted = copy.deepcopy(added)
    converted['id'] = plan['id']
    config.write_text(yaml.safe_dump(dict(schema=1, sections={'device': [converted]}), allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='must match current plans'):
        refresh(tmp_cfg, model, 'device', raw, expected_sha256=digest(raw))


@pytest.mark.parametrize('change', ['facts', 'appendix'])
def test_noop_still_verifies_the_scenario_appendix(tmp_cfg, scenario_prose, change):
    section, model, _, agent = scenario_prose
    raw = Generator(tmp_cfg, model, agent).run()[0].read_bytes()
    if change == 'facts':
        model.scenarios[section['scenario']].messages[0].name = 'changedCall'
    else:
        metadata, body = split_frontmatter(raw.decode().replace('\r\n', '\n'))
        body = body.replace('FrameFactory::createFrame()', 'FrameFactory::differentCall()')
        metadata['generated_design']['body_sha256'] = digest(body.strip().encode())
        raw = ('---\n'+yaml.safe_dump(metadata, allow_unicode=True)+'---\n'+body).encode()
    with pytest.raises(ValueError, match='Scenario evidence|Scenario appendix|LLM 설계 입력'):
        refresh(tmp_cfg, model, section['id'], raw, expected_sha256=digest(raw))
