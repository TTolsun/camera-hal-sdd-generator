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
