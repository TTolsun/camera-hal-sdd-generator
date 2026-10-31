import pytest
from sdd.translation_checks import required_phrases

RULE=dict(source_all=['프로세스'],source_any=['원복','복구'],
          english_any=['separate processes','independent processes'],
          english_none=['by the unmodified official cam'],expected_matches=1)

def test_independent_invocations_cannot_replace_independent_processes():
    source='세 독립 프로세스에서 실행한 뒤 커널을 원복했습니다.'
    assert source in required_phrases({source:'Three independent invocations were executed.'},[RULE])
    assert not required_phrases({source:'It ran in three separate processes before restoration.','다른 항목':'Other item.'},[RULE])
    assert source in required_phrases({source:'Three independent processes were run by the unmodified official cam.'},[RULE])

@pytest.mark.parametrize('strings',[{}, {'프로세스 원복':'Independent processes','프로세스 복구':'Independent processes'}])
def test_missing_or_ambiguous_source_scope_fails(strings):
    with pytest.raises(ValueError,match='unexpected number'):required_phrases(strings,[RULE])
