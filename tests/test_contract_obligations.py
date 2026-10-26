from sdd.semantic import only_uncertainty, review
from sdd.facts.model import KnowledgeModel


def test_caller_check_is_a_claim_that_requires_evidence():
    text = '호출자는 cameras()를 호출하기 전에 매니저가 실행 중인지 확인해야 합니다.'
    assert not only_uncertainty(text)
    assert review(text, KnowledgeModel(), set()) == ['설명 문단에 근거 인용이 없습니다.']
    assert review(text + ' `manager.cpp:1`.', KnowledgeModel(), {'manager.cpp:1'}) == []


def test_unverified_runtime_result_remains_uncertain():
    assert only_uncertainty('종료 순서는 코드를 실행해서 확인해야 합니다.')
    assert only_uncertainty('이 호출 순서는 소스에 명시되지 않았습니다.')


def test_implementation_check_does_not_exempt_evidence():
    assert not only_uncertainty('구현자는 입력 버퍼의 상태를 확인해야 합니다.')


def test_negative_guarantee_is_a_claim_that_requires_evidence():
    text = '카메라 상태 함수는 동기화를 보장하지 않으며 호출자가 동기화를 책임져야 합니다.'
    assert not only_uncertainty(text)
    assert review(text, KnowledgeModel(), set()) == ['설명 문단에 근거 인용이 없습니다.']
    assert review(text + ' `camera.cpp:781`.', KnowledgeModel(), {'camera.cpp:781'}) == []


def test_missing_evidence_does_not_become_a_negative_contract():
    assert only_uncertainty('근거가 부족하여 동기화를 보장하지 않는지는 알 수 없습니다.')


def test_conditional_absence_is_a_branch_not_missing_evidence():
    text = 'createIPA()는 모듈이 존재하지 않으면 nullptr를 반환합니다.'
    assert not only_uncertainty(text)
    assert review(text, KnowledgeModel(), set()) == ['설명 문단에 근거 인용이 없습니다.']
    assert review(text + ' `ipa_manager.h:40`.', KnowledgeModel(), {'ipa_manager.h:40'}) == []
    assert only_uncertainty('모듈이 존재하지 않으면 어떤 값을 반환하는지 알 수 없습니다.')


def test_option_absence_does_not_deny_enclosing_class():
    from sdd.facts.model import KnowledgeModel, ClassInfo
    model = KnowledgeModel()
    model.classes['ns::Benchmark'] = ClassInfo('ns::Benchmark')
    text = '`Benchmark` 생성자는 설정이 존재하지 않을 경우 초기값을 유지합니다 `x.h:1`.'
    assert review(text, model, {'x.h:1'}) == []
    assert review('`Benchmark` 클래스는 존재하지 않습니다 `x.h:1`.', model, {'x.h:1'})
