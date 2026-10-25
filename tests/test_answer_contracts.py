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
    with pytest.raises(ValueError, match='한두 문단'):
        validate(topic,answers[:1])
    wrong=copy.deepcopy(answers);wrong[1]['evidence']=['source']
    with pytest.raises(ValueError, match='다른 분할'):
        validate(topic,wrong)
    wrong=copy.deepcopy(answers);wrong[1]['part_id']={}
    with pytest.raises(ValueError, match='id'):
        validate(topic,wrong)
