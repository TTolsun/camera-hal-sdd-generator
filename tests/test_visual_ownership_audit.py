"""Ownership diagram audit tests with archived graph language and synthetic verdicts."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from sdd import generated_visuals, visual_audit_gate
from sdd.config import load
from sdd.decision_passages import decision_locations
from sdd.facts.model import KnowledgeModel
from test_inhouse_template import TEMPLATE


FENCE = r'''/**
 * A Fence is constructed with a UniqueFD whose ownership is moved in the Fence.
 * A FrameBuffer can be associated with a Fence by passing it to the
 * Request::addBuffer() function, which will move the Fence into the FrameBuffer
 * itself. Once a Request is queued to the Camera, a preparation phase
 * guarantees that before actually applying the Request to the hardware, all the
 * valid fences of the frame buffers in a Request are correctly signalled.
 * If waiting on a Fence fails, the FrameBuffer's fence is not reset and is made
 * available to application for them to handle it, by releasing the Fence to
 * correctly close the underlying UniqueFD. The Request completes in failed state.
 */'''
STOP = r'''/**
 * \subsubsection Stopping
 * The camera has been asked to stop. Pending requests are being completed or
 * cancelled, and no new requests are permitted to be queued. The camera will
 * transition to the Configured state when all queued requests have been
 * returned to the application.
 */'''


def node(ident, symbol, ko, en, source='fence'):
    return dict(id=ident, symbol=symbol, shape='box', label=ko, label_en=en, quote_ids=[source + ':0'])


def edge(start, end, ko, en, source='fence'):
    return {'from': start, 'to': end, 'label': ko, 'label_en': en, 'condition_ref': 'always',
            'quote_ids': [source + ':0']}


@pytest.fixture
def ownership(tmp_cfg, monkeypatch):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.max_input_chars = 30_000
    cfg = load(TEMPLATE / 'sdd.yaml')
    section = cfg.section('vendor-contract')
    topic = next(t for t in section['design_topics'] if t['id'] == 'ownership')
    plan = next(p for p in yaml.safe_load((TEMPLATE / 'config/visuals.yaml').read_bytes())['sections']['vendor-contract']
                if p['id'] == 'buffer-ownership')
    monkeypatch.setattr(generated_visuals, 'definitions', lambda cfg, section: [plan])
    evidence = {}
    for key, text in {'fence': FENCE, 'stop': STOP}.items():
        source = dict(id=key, file=key + '.cpp', start='/**', end=' */')
        topic['sources'].append(source)
        evidence['vendor-contract/ownership/' + key] = dict(
            selector=source, file=source['file'], line=1, text=text, status='available',
            sha256=hashlib.sha256(text.encode()).hexdigest(), commit='a' * 40)
    return section, plan, KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence=evidence)


@pytest.fixture
def graphs():
    # These three nodes and two arrows are the reversed branch in release-draft.
    before = {'nodes': [
        node('fd', 'UniqueFD', 'UniqueFD는 Fence를 만들 때 소유권이 Fence로 이동합니다.',
             'Ownership of the UniqueFD moves into the Fence when it is constructed.'),
        node('fence', 'Fence', 'Fence 대기에 실패하면 애플리케이션은 기반 UniqueFD가 올바르게 닫히도록 Fence를 해제해 처리해야 하며, Request는 실패 상태로 완료됩니다.',
             'If waiting for a Fence fails, the application must handle it by releasing the Fence so that the underlying UniqueFD is correctly closed, and the Request completes in a failed state.'),
        node('buffer', 'FrameBuffer', 'FrameBuffer에 연결된 fence가 완료되면 라이브러리가 fence를 해제하므로 애플리케이션은 그 fence에 접근할 수 없습니다. 대기에 실패하면 fence는 초기화되지 않고 애플리케이션이 처리할 수 있도록 제공됩니다.',
             "When a FrameBuffer's fence completes, the library releases the fence, so the application cannot access it. If waiting fails, the fence is not reset and is made available to the application for handling."),
    ], 'edges': [
        edge('fd', 'fence', 'Fence를 생성할 때 UniqueFD의 소유권이 이동합니다.',
             'Ownership of the UniqueFD moves when the Fence is constructed.'),
        edge('fence', 'buffer', 'Request::addBuffer()에 전달하면 Fence가 FrameBuffer로 이동합니다.',
             'Passing the Fence to Request::addBuffer() moves it into the FrameBuffer.'),
    ]}
    after = {'nodes': [
        node('attach', 'FrameBuffer', '요청에 버퍼와 펜스를 연결합니다.', 'Attach the buffer and its fence to the request.'),
        node('wait', 'Fence', '큐에 들어간 요청을 준비하며 펜스를 대기합니다.', 'Wait for the fence while preparing a queued request.'),
        node('failure', 'Request', '대기에 실패하면 요청이 실패 상태로 완료됩니다.', 'If waiting fails, the request completes in a failed state.'),
        node('cleanup', 'Fence', '애플리케이션은 재사용 전에 남은 펜스의 해제를 확인합니다.', 'Before reuse, the application checks that the retained fence was released.'),
        node('stop', 'Stopping', '정지 중에는 대기 요청을 완료하거나 취소합니다.', 'While stopping, complete or cancel pending requests.', 'stop'),
        node('return', 'Configured', '큐에 들어간 모든 요청을 애플리케이션에 반환하면 Configured로 전환합니다.',
             'Transition to Configured when all queued requests have been returned to the application.', 'stop'),
        node('consumer', 'application', '덮어쓰기 전 마지막 외부 소비자의 사용 종료와 동기화를 별도로 확인하세요. 확인 주체는 발췌에서 명시되지 않습니다.',
             'Before overwriting, separately verify the last external consumer has finished and synchronization is complete. The excerpt does not identify who verifies this.', 'stop'),
    ], 'edges': [
        edge('attach', 'wait', '실제 큐 진입 이후 준비합니다.', 'Prepare after actual queue entry.'),
        edge('wait', 'failure', '대기가 실패하면 요청이 실패 상태로 완료됩니다.', 'If the wait fails, the request completes in a failed state.'),
        edge('failure', 'cleanup', '실패한 펜스를 해제합니다.', 'Release the fence after the wait failure.'),
        edge('stop', 'return', '모든 큐 요청을 애플리케이션에 반환하면 전환합니다.', 'Transition when all queued requests have been returned to the application.', 'stop'),
    ]}
    return before, after


def test_old_reverse_edge_is_rejected_and_corrected_at_generation(tmp_cfg, ownership, graphs, monkeypatch):
    section, plan, model = ownership
    old, corrected = graphs
    tags = []
    diagnostics = []
    monkeypatch.setattr('sdd.repair_diagnostics.observe_attempt', lambda *args, **kwargs: diagnostics.append(kwargs))
    archive = tmp_cfg.build_dir / 'prompts' / 'calls' / 'fixture'
    agent = SimpleNamespace()

    def chat(system, user, *, tag, response_schema):
        tags.append(tag)
        agent.last_receipt = archive / f'{len(tags):03d}.receipt.json'
        if not tag.endswith('_audit'):
            if tag.endswith('_1'):
                assert 'fence -> buffer' in user
                return json.dumps(corrected, ensure_ascii=False)
            return json.dumps(old, ensure_ascii=False)
        payload = json.loads(user)
        assert 'Korean and English separately' in system
        assert '같은 요청의 처음 연결로 되돌아가는 역순' in system
        assert payload['sources'] == {'fence': FENCE, 'stop': STOP}
        if payload['draft'] == old:
            return json.dumps(dict(passed=False, reason='fence -> buffer reverses failure and association.'))
        assert payload['draft'] == corrected
        return json.dumps(dict(passed=True, reason='Direction, stop boundary and separate consumer check confirmed.'))

    agent.chat = chat
    artifact = generated_visuals.generate(tmp_cfg, model, section, agent)
    record = artifact['records'][plan['id']]
    assert record['draft'] == corrected
    assert tags == ['visual_vendor-contract_buffer-ownership_0', 'visual_vendor-contract_buffer-ownership_0_audit',
                    'visual_vendor-contract_buffer-ownership_1', 'visual_vendor-contract_buffer-ownership_1_audit']
    assert record['generation_audit']['receipt'] == 'fixture/004.receipt.json'
    assert [item['receipt'].name for item in diagnostics] == ['001.receipt.json', '003.receipt.json']
    assert [item['details']['audit_receipt'] for item in diagnostics] == ['fixture/002.receipt.json', 'fixture/004.receipt.json']
    assert [json.loads(item['raw']) for item in diagnostics] == [old, corrected]
    assert generated_visuals.resolve(tmp_cfg, model, section, artifact) == [record['graph']]
    corrupt = deepcopy(artifact)
    corrupt['records'][plan['id']]['generation_audit']['input_sha256'] = 'a' * 64
    with pytest.raises(ValueError, match='does not match the saved draft'):
        generated_visuals.resolve(tmp_cfg, model, section, corrupt)


def test_semantic_audit_keeps_full_input_and_fails_at_budget(tmp_cfg, ownership, graphs):
    section, plan, model = ownership
    _, records, passages, _, request = generated_visuals.inputs(tmp_cfg, model, section, plan)
    tmp_cfg.agent.max_input_chars = 1_000

    def no_call(*args, **kwargs):
        pytest.fail('an oversized request must never reach the CLI')

    with pytest.raises(ValueError, match='input budget'):
        visual_audit_gate.review(tmp_cfg, SimpleNamespace(chat=no_call), plan, request,
                                 records, passages, graphs[1], 'ownership')


def test_stop_and_fence_retrieval_are_prioritized_by_template(tmp_cfg, ownership):
    section, _, model = ownership
    topic = next(t for t in section['design_topics'] if t['id'] == 'ownership')
    commit = model.meta['source_commit']
    matches = {'stop': [(False, False, 1, 'stop.cpp', 5)], 'fence': [(False, False, 1, 'fence.cpp', 9)],
               'lifetime': [(False, False, 1, 'other.cpp', 12)]}
    cache = {('decision-passages', commit): matches}
    picks = list(decision_locations(tmp_cfg, commit, (), section, topic, cache))
    assert picks[:2] == [('stop.cpp', 5), ('fence.cpp', 9)]
