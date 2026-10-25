import pytest
from sdd.semantic import only_uncertainty, review
from sdd.facts.model import KnowledgeModel


@pytest.mark.parametrize('text', [
    '파일이 존재하지 않으면 함수는 대체 파일을 검색합니다.',
    '대체 파일이 존재하지 않을 때 함수는 빈 문자열을 반환합니다.',
    '함수는 설정을 조정하고 상태를 반환하며, 호출자는 변경된 설정을 확인해야 합니다.',
    'Adjusted를 반환받은 호출자는 반드시 조정된 설정을 다시 확인해야 합니다.',
    '함수는 요청을 반환하며, 완료 순서는 기기에서 확인해야 합니다.',
])
def test_concrete_conditions_and_caller_contracts_still_require_evidence(text):
    assert not only_uncertainty(text)
    assert '설명 문단에 근거 인용이 없습니다.' in review(text, KnowledgeModel(), set())


@pytest.mark.parametrize('text', [
    '실행 스레드는 정적 분석으로 확인할 수 없습니다.',
    '종료 순서는 기기에서 확인해야 합니다.',
    '지원하는 클래스는 추출되지 않았습니다.',
])
def test_pure_unknowns_remain_unknown(text):
    assert only_uncertainty(text)
def test_assertion_check_is_a_factual_claim_requiring_a_citation():
    from sdd.semantic import only_uncertainty, review
    from sdd.facts.model import KnowledgeModel
    text = '이 핸들러에서는 ASSERT(state_ != Stopped)와 같은 상태 확인이 필요합니다.'
    assert not only_uncertainty(text)
    assert review(text, KnowledgeModel(), set()) == ['설명 문단에 근거 인용이 없습니다.']
    assert only_uncertainty('실제 콜백의 실행 스레드는 별도 확인이 필요합니다.')

