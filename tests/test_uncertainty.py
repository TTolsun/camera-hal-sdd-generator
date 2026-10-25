import pytest
from sdd.semantic import only_uncertainty, review
from sdd.facts.model import KnowledgeModel


@pytest.mark.parametrize('text', [
    '파일이 존재하지 않으면 함수는 대체 파일을 검색합니다.',
    '대체 파일이 존재하지 않을 때 함수는 빈 문자열을 반환합니다.',
    '함수는 설정을 조정하고 상태를 반환하며, 호출자는 변경된 설정을 확인해야 합니다.',
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
