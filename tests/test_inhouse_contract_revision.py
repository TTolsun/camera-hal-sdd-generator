"""Exercise the in-house revision requests with synthetic CLI responses."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from sdd import first_run, generated_design, generated_visuals
from sdd.config import load
from sdd.facts.model import KnowledgeModel
from test_inhouse_template import TEMPLATE


QUEUE = (
    'Camera::queueRequest returns 0 on success or a negative error code otherwise. '
    'Once the request has been queued, the camera will notify its completion through requestCompleted. '
    'Returns EINVAL for an invalid request without queuing it.'
)
METADATA = (
    'FrameError: sequence and timestamp are valid. Other metadata fields may be invalid. '
    'FrameCancelled: All fields but status are invalid.'
)


@pytest.fixture
def contract(tmp_cfg):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.max_input_chars = 30_000
    section = load(TEMPLATE / 'sdd.yaml').section('vendor-contract')
    section.pop('reader_profile')
    model = KnowledgeModel(meta={'source_commit': 'a' * 40})
    for topic in section['design_topics']:
        if topic['id'] not in ('completion', 'failure'):
            continue
        excerpts = {'queue': QUEUE, 'metadata': METADATA}
        for sid, text in excerpts.items():
            source = dict(id=sid, file='camera.cpp', start=text[:15], end=text[-15:])
            topic['sources'].append(source)
            model.evidence[f"vendor-contract/{topic['id']}/{sid}"] = dict(
                selector=source, file=source['file'], line=1 if sid == 'queue' else 2,
                status='available', commit='a' * 40, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    return section, model


def test_inhouse_completion_revises_timing_and_field_validity(tmp_cfg, contract):
    section, model = contract
    topic = next(t for t in section['design_topics'] if t['id'] == 'completion')
    section['design_topics'] = [topic]
    section['design_requirements'] = [r for r in section['design_requirements'] if r['id'] == 'completion']
    initial = [
        '요청 제출은 성공 시 0을 반환하며, 큐에 들어간 요청의 완료는 이후 `requestCompleted` 신호로 통지됩니다.',
        '`FrameError`는 `sequence`와 `timestamp`만 유효합니다.',
        '`FrameCancelled`는 `status`만 유효합니다.',
    ]
    expected = [
        '제출 호출은 성공 시 0을 반환합니다. 큐에 들어간 요청은 완료 시 `requestCompleted`로 통지됩니다.',
        '`FrameError`에서 `sequence`와 `timestamp`는 유효하며 다른 메타데이터 필드는 유효하지 않을 수 있습니다.',
        initial[2],
    ]

    def response(texts):
        return json.dumps({'statements': [dict(text=text, quote_id=f'{sid}:0', evidence=[sid],
            covers=['completion'], kind='behavior') for text, sid in zip(texts, ('queue', 'metadata', 'metadata'))]},
            ensure_ascii=False)

    calls = []

    def chat(system, user, *, tag, response_schema):
        calls.append(tag)
        assert QUEUE in user and METADATA in user
        if not tag.endswith('_revision'):
            assert 'Revision requirements' not in user
            return response(initial)
        assert response(initial) in user
        assert '큐 진입 조건을 반환 이후의 완료 통지 보장으로 표현했다면 고치세요.' in user
        assert '오류 상태에서는 유효하다고 명시된 필드와 나머지의 가능성 또는 제한을 빠짐없이' in user
        return response(expected)

    result = generated_design.generate(tmp_cfg, model, SimpleNamespace(chat=chat), section)
    assert [a['text'] for a in result.artifact['answers']['completion']] == expected
    assert result.artifact['grounding_review'] == 'not-run'
    assert calls == ['vendor-contract_completion_0', 'vendor-contract_completion_0_revision']


@pytest.mark.parametrize('visual_id', ['request-flow', 'request-failures'])
def test_inhouse_graph_revision_preserves_source_conditions_in_both_languages(tmp_cfg, contract, monkeypatch, visual_id):
    section, model = contract
    plan = next(p for p in yaml.safe_load((TEMPLATE / 'config/visuals.yaml').read_bytes())['sections']['vendor-contract']
                if p['id'] == visual_id)
    monkeypatch.setattr(generated_visuals, 'plans', lambda cfg, section: [plan])
    initial_labels = ('카메라에 request를 큐에 넣습니다. 성공하면 0을 반환하고, 그렇지 않으면 음수 오류 코드를 반환합니다.',
                      'Queues a request to the camera. It returns 0 on success or a negative error code otherwise.')
    expected_labels = ('요청 제출 함수를 호출합니다.', 'Call the request submission function.')
    failure = visual_id == 'request-failures'
    result = ('유효하지 않으면 큐에 넣지 않습니다.', 'Reject an invalid request without queuing it.') if failure else (
              '큐에 들어간 요청의 완료를 통지합니다.', 'Notify completion of a queued request.')
    target = 'EINVAL' if failure else 'requestCompleted'
    initial = {'nodes': [dict(id='submit', symbol='queueRequest', shape='box', label=initial_labels[0],
                             label_en=initial_labels[1], quote_ids=['queue:0']),
                        dict(id='result', symbol=target, shape='box', label=result[0], label_en=result[1],
                             quote_ids=['queue:0'])],
               'edges': [{'from': 'submit', 'to': 'result', 'label': result[0], 'label_en': result[1],
                          'condition_ref': 'always', 'quote_ids': ['queue:0']}]}
    expected = deepcopy(initial)
    expected['nodes'][0].update(label=expected_labels[0], label_en=expected_labels[1])
    expected['nodes'].append(dict(id='returned', symbol='queueRequest', shape='box',
        label='성공 시 0을, 실패 시 음수 오류 코드를 반환합니다.',
        label_en='Returns 0 on success or a negative error code on failure.', quote_ids=['queue:0']))
    expected['edges'].append({'from': 'submit', 'to': 'returned', 'label': '제출 함수의 반환',
        'label_en': 'Submission return', 'condition_ref': 'always', 'quote_ids': ['queue:0']})
    if failure:
        for node in expected['nodes'][1:]:
            node['shape'] = 'outcome'
    calls = []

    def chat(system, user, *, tag, response_schema):
        calls.append(tag)
        assert QUEUE in user
        if not tag.endswith('_revision'):
            return json.dumps(initial, ensure_ascii=False)
        assert json.dumps(initial, ensure_ascii=False) in user
        assert plan['revision_prompt'] in user
        assert '한국어와 영어' in plan['revision_prompt']
        if failure:
            assert '오류로 이어지는 모든 화살표의 시작 라벨' in user
            assert '반환에서 후속 처리나 통지로 나가는 화살표' in user
            assert 'outcome' in response_schema['properties']['nodes']['items']['properties']['shape']['enum']
        else:
            assert '반환 이후 통지라는 시간 보장' in user
        return json.dumps(expected, ensure_ascii=False)

    artifact = generated_visuals.generate(tmp_cfg, model, section, SimpleNamespace(chat=chat))
    record = artifact['records'][visual_id]
    assert record['draft'] == expected
    assert record['graph']['nodes'][0]['label'] == expected_labels[0]
    assert record['graph']['nodes'][0]['label_en'] == expected_labels[1]
    assert 'revision_prompt' not in record['graph']
    assert calls == [f'visual_vendor-contract_{visual_id}_0', f'visual_vendor-contract_{visual_id}_0_revision']
    if failure:
        followup = deepcopy(expected)
        followup['nodes'].append(dict(id='completion', symbol='requestCompleted', shape='outcome',
            label='요청 완료 통지', label_en='Request completion signal', quote_ids=['queue:0']))
        followup['edges'].append({'from': 'returned', 'to': 'completion', 'label': '큐에 들어간 요청을 처리합니다.',
            'label_en': 'Process the queued request.', 'condition_ref': 'always', 'quote_ids': ['queue:0']})
        with pytest.raises(ValueError, match='no outgoing arrow'):
            generated_visuals.materialize(tmp_cfg, model, section, plan, followup, 'fixture')

        disconnected = deepcopy(expected)
        disconnected['nodes'].append(dict(id='frame_error', symbol='FrameError', shape='box',
            label='다른 필드는 유효하지 않을 수 있습니다.', label_en='Other fields may be invalid.',
            quote_ids=['metadata:0']))
        with pytest.raises(ValueError, match='disconnected IDs: frame_error'):
            generated_visuals.materialize(tmp_cfg, model, section, plan, disconnected, 'fixture')


def test_inhouse_evidence_selection_receives_contract_scope(tmp_cfg, contract):
    section, _ = contract
    topic = next(t for t in section['design_topics'] if t['id'] == 'completion')
    entry = dict(file='camera.cpp', line=1, text=QUEUE)
    prompt, selectors = first_run._request(tmp_cfg, section, topic, [(entry, topic['sources'][0])])
    assert list(selectors) == ['window-1']
    assert json.loads(prompt)['writing_instructions'] == topic['prompt']
