import copy

import pytest
import yaml
from pathlib import Path

from sdd.answer_contracts import check, configuration_errors, sourced_check_obligation, validate


def statement(text, **kw):
    return dict(text=text, kind='behavior', evidence=['source'], **kw)


def test_status_checks_use_identifier_boundaries_and_alternatives():
    rule = dict(basis='description', required_terms=[['Valid'], ['Invalid'], ['null', 'nullptr']])
    with pytest.raises(ValueError, match='Valid'):
        check(rule, [statement('Invalid, nullptr')], 'status')
    check(rule, [statement('Invalid 또는 Valid이며 실패 시 nullptr를 반환합니다.')], 'status')


def test_obligation_does_not_become_observed_implementation():
    rule = dict(basis='contract')
    # Actual old 9B answer, including the error-state omission.
    bad = '`PipelineHandler::stopDevice` 함수는 캡처를 즉시 중단하고 처리 중인 요청들을 완료 상태로 만듭니다.'
    with pytest.raises(ValueError, match='구현 의무'):
        check(rule, [statement(bad)], 'shutdown')
    check(rule, [statement('구현자는 남은 요청을 취소하여 오류 상태로 완료해야 합니다.')], 'shutdown')
    # The common rule also applies to identifiers unrelated to libcamera.
    with pytest.raises(ValueError, match='구현 의무'):
        check(rule, [statement('Device::flush()는 버퍼 수명을 보장합니다.')], 'device')
    check(rule, [statement('Device::flush() 구현자는 작업 완료 전 버퍼를 해제해서는 안 됩니다.')], 'device')


def test_call_context_does_not_prove_thread_safety():
    rule = dict(basis='contract', reject_patterns=[dict(
        pattern=r'(스레드\s*안전성|스레드\s*안전).{0,30}보장(?:합니다|된다|됩니다|한다)',
        message='호출 문맥을 안전성 보장으로 바꾸지 마세요.')])
    old = '`completeBuffer` 함수는 반드시 `CameraManager` 스레드에서 호출되어야 하며, 이는 요청 처리의 순서와 스레드 안전성을 보장합니다.'
    with pytest.raises(ValueError):
        check(rule, [statement(old)], 'context')
    check(rule, [statement('호출자는 지정된 스레드에서 호출해야 합니다. 이 조건만으로 스레드 안전성을 보장하지는 않습니다.')], 'context')


def test_sourced_caller_check_is_not_uncertainty():
    text = 'Adjusted인 경우 호출자는 조정된 설정을 다시 확인해야 합니다.'
    assert sourced_check_obligation(text, 'The caller shall check the configuration carefully.')
    assert not sourced_check_obligation(text, 'The implementation is unknown.')
    assert not sourced_check_obligation('동작을 확인할 수 없어 호출자가 확인해야 합니다.', 'The caller shall check.')
    assert sourced_check_obligation('호출자는 해당 구성이 유효해졌지만 스트림 파라미터가 변경되었거나 일부 스트림 구성이 제거되었을 수 있으므로 반드시 최신 구성을 세심하게 확인해야 합니다.', 'The caller shall check the configuration carefully.')
    check(dict(basis='contract'), [statement('구현자는 요청의 완료를 신호로 보내야 합니다.')], 'completion')
    check(dict(basis='contract'), [statement('이 함수는 지정된 스레드에서 호출되어야 하며 입력 상태를 유지해야 합니다.')], 'context')


def test_observed_invalid_disjunction_is_rejected_by_project_rule():
    config = Path(__file__).parents[1] / 'examples/libcamera/config/sections.yaml'
    section = next(s for s in yaml.safe_load(config.read_text(encoding='utf-8'))['sections'] if s['id']=='vendor-assurance')
    topic = next(t for t in section['design_topics'] if t['id']=='constraints')
    rule = next(p['answer_contract'] for p in topic['parts'] if p['id']=='invalid')
    with pytest.raises(ValueError, match='또는 조건'):
        check(rule, [statement('설정이 수정될 수 없거나 극단적인 경우에만 Invalid 상태를 반환합니다.')], 'invalid')
    check(rule, [statement('Invalid는 구성이 유효하지 않고 조정할 수 없다는 뜻입니다. 빈 구성과 같은 극단적인 경우에만 발생할 수 있습니다.')], 'invalid')


def test_queue_return_cannot_become_capture_queue_success():
    config = Path(__file__).parents[1] / 'examples/libcamera/config/sections.yaml'
    section = next(s for s in yaml.safe_load(config.read_text(encoding='utf-8'))['sections']
                   if s['id'] == 'camera-requests')
    topic = next(t for t in section['design_topics'] if t['id'] == 'request')
    part = next(p for p in topic['parts'] if p['id'] == 'completion-signal')
    rule = part['answer_contract']
    prefix = '`Camera::queueRequest()`는 `ConnectionTypeQueued`를 지정한 `invokeMethod`를 호출합니다. '
    suffix = ' 완료는 `requestCompleted` 신호로 알립니다.'
    # Keep every required identifier: the wrong success condition must still fail.
    for result in ('캡처 큐에 넣는 데 성공하면 0을 반환합니다.', '장치 큐잉 성공 시 0을 반환합니다.'):
        with pytest.raises(ValueError, match='큐잉 성공'):
            check(rule, [statement(prefix + result + suffix)], 'completion-signal')
    check(rule, [statement(prefix + '그 호출 뒤 0을 반환합니다.' + suffix)], 'completion-signal')


@pytest.mark.parametrize('rule', [None, {}, {'basis':'guaranteed'}, {'basis':'contract','answer':'fixed'},
    {'basis':'contract','required_terms':['WrongShape']},
    {'basis':'contract','reject_patterns':[{'pattern':'[','message':'bad regex'}]}])
def test_bad_contract_fails_before_model(rule):
    assert configuration_errors(dict(answer_contract=rule))


def test_part_coverage_and_source_scope_are_revalidated():
    topic = dict(id='device', parts=[dict(id='acquire', sources=['source'], answer_contract=dict(basis='contract')),
                                    dict(id='release', sources=['other'], answer_contract=dict(basis='contract'))])
    answers=[statement('호출자는 자원을 확보해야 합니다.',part_id='acquire'),
             dict(text='호출자는 자원을 반환해야 합니다.',kind='behavior',evidence=['other'],part_id='release')]
    validate(topic,answers)
    with pytest.raises(ValueError, match='답변 수'):
        validate(topic,answers[:1])
    wrong=copy.deepcopy(answers);wrong[1]['evidence']=['source']
    with pytest.raises(ValueError, match='다른 분할'):
        validate(topic,wrong)
    wrong=copy.deepcopy(answers);wrong[1]['part_id']={}
    with pytest.raises(ValueError, match='id'):
        validate(topic,wrong)


def test_actual_qwen_postincrement_error_is_rejected_by_project_contract():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / 'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))
    topic = next(t for s in data['sections'] if s['id'] == 'pipeline-requests'
                 for t in s['design_topics'] if t['id'] == 'queue')
    rule = next(p['answer_contract'] for p in topic['parts'] if p['id'] == 'submit-tracking')
    tracking = '요청을 queuedRequests_에 추가합니다. '
    bad = 'requestSequence_ 값을 증가시키고 그 증가된 값을 sequence_에 저장합니다.'
    with pytest.raises(ValueError):
        check(rule, [statement(tracking + bad)], 'submit-tracking')
    with pytest.raises(ValueError, match='후위'):
        check(rule, [statement(tracking + '증가 전 값을 버리고 requestSequence_의 증가된 값을 sequence_에 저장합니다.')], 'submit-tracking')
    for text in ['sequence_에는 requestSequence_의 증가 전 값을 저장하고 카운터는 후위 증가합니다.',
                 'requestSequence_의 이전 값이 sequence_에 대입된 뒤 requestSequence_가 증가합니다.']:
        check(rule, [statement(tracking + text)], 'submit-tracking')


def test_reuse_fence_recommendation_is_not_strengthened_to_must_not():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / 'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))
    topic = next(t for s in data['sections'] if s['id'] == 'camera-requests'
                 for t in s['design_topics'] if t['id'] == 'lifetime')
    rule = next(p['answer_contract'] for p in topic['parts'] if p['id'] == 'reuse-fences')
    assert rule['basis'] == 'description'
    buffers = 'ReuseBuffers로 기존 버퍼를 유지해도 '
    check(rule, [statement(buffers + '펜스는 재사용되지 않으며, 펜스를 쓰는 경우 이 플래그를 피하도록 권고합니다.')], 'fence')
    with pytest.raises(ValueError, match='should not'):
        check(rule, [statement(buffers + '펜스를 사용하는 경우 이 플래그 사용은 권고되지 않으며 사용해서는 안 됩니다.')], 'fence')
def test_explicit_answer_budget_keeps_coverage_and_saved_answer_limit():
    topic = dict(id='branch', parts=[dict(id='flow', sources=['source'], max_statements=3,
        answer_contract=dict(basis='implementation', required_terms=[['condition'], ['return']]))])
    answers = [statement('condition을 검사합니다.', part_id='flow'),
               statement('조건이 참이면 return을 실행합니다.', part_id='flow')]
    validate(topic, answers)
    with pytest.raises(ValueError, match='필수 용어'):
        validate(topic, answers[:1])
    with pytest.raises(ValueError, match='답변 수'):
        validate(topic, answers * 2)
    topic['parts'][0].pop('answer_contract')
    with pytest.raises(ValueError, match='id'):
        validate(topic, [{k:v for k,v in answer.items() if k != 'part_id'} for answer in answers])


def test_reader_observed_state_and_void_owner_errors_are_rejected():
    root = Path(__file__).resolve().parents[1]
    sections = yaml.safe_load((root/'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))['sections']
    section = next(s for s in sections if s['id']=='request-lifecycle')
    detail = next(s for s in sections if s['id']=='request-diagnosis')
    topic = next(t for t in detail['design_topics'] if t['id']=='configuration-failure')
    rule = next(p['answer_contract'] for p in topic['parts'] if p['id']=='entry')
    with pytest.raises(ValueError, match='상태 범위'):
        check(rule, [statement('Camera::configure의 isAccessAllowed 반환을 관찰하면 CameraAcquired이고 CameraConfigured인지 확인합니다.')], 'entry')
    topic = next(t for t in section['design_topics'] if t['id']=='journey')
    with pytest.raises(ValueError, match='void'):
        check(topic['answer_contract'], [statement('PipelineHandler::doQueueRequest() 함수는 성공 시 0을 반환합니다.')], 'journey')


@pytest.mark.parametrize('text', ['quote_id 기록 항목은 근거 매핑이 없어 지지하지 않습니다.',
                                  'source:0의 근거 매핑을 기록하세요.'])
def test_investigation_rejects_generator_verdict_in_reader_prose(text):
    rule = dict(basis='investigation')
    with pytest.raises(ValueError, match='quote_id'):
        check(rule, [statement(text)], 'record')
    check(rule, [dict(statement('quote_id 값을 조사 기록 항목으로 제안합니다.'),
                     quote='int quote_id = 0;')], 'record')
