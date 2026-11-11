import copy
import json
import pytest
from sdd.review_context import ENCODING,REFERENCE,pack,prepare,unpack


def test_repeated_source_and_nested_presentation_round_trip_without_hidden_scope_loss():
    source='if (!request) { return -EINVAL; }\n'*80
    path=[{'tag':'main','attrs':{'hidden':'','aria-hidden':'true'},'position':3},
          {'tag':'section','attrs':{'id':'한영 조건 / exact%20literal'},'position':7}]
    original={'items':[{'id':str(i),'source':source,'presentation':path,
                       'conditions':['true','false'],'unreviewed_scope':['physical device']} for i in range(12)]}
    snapshot=copy.deepcopy(original);encoded=pack(original)
    assert unpack(encoded)==original==snapshot
    assert len(json.dumps(encoded)) < len(json.dumps(original))/2
    text,package,proof=prepare(original)
    assert package and proof['round_trip'] and proof['original_sha256']==proof['reconstructed_sha256']
    assert 'not a summary' in text and 'hidden' in text and 'physical device' in text


def test_literal_reference_looking_source_remains_source_text():
    text='Source says '+json.dumps({REFERENCE:'v0'})+' 한글\n'*100
    original={'source':[text,text],'types':[None,True,False,0,1,1.0,'1']}
    assert unpack(pack(original))==original


def test_shared_parent_does_not_keep_single_use_child_pool_entries():
    parent={'source':'exact source clause\n'*100,'conditions':['if A','otherwise']}
    original={'items':[parent for _ in range(12)]}
    package=pack(original)
    assert unpack(package)==original
    assert len(package['shared_values'])==1
    assert next(iter(package['shared_values'].values()))==parent


def test_reserved_object_key_fails_instead_of_changing_its_meaning():
    with pytest.raises(ValueError,match='reserved'):
        pack({'source':{REFERENCE:'authored reference'}})


def test_missing_cyclic_mixed_and_unused_references_fail():
    for shared,payload in [({}, {REFERENCE:'missing'}),
                           ({'v0':{REFERENCE:'v0'}},{REFERENCE:'v0'}),
                           ({'v0':'text'},{REFERENCE:'v0','extra':'hidden condition'}),
                           ({'v0':'unused'},'text')]:
        with pytest.raises(ValueError):
            unpack(dict(encoding=ENCODING,shared_values=shared,payload=payload))


def test_unique_small_json_keeps_the_existing_plain_prompt():
    value={'question':'Why?','condition':False,'source':'return 0;'}
    text,package,proof=prepare(value)
    assert package is None and json.loads(text)==value and proof['encoding']=='plain-json'


@pytest.mark.parametrize('value',[{1:'not a JSON string key'},{'source':float('nan')},{'source':object()}])
def test_non_json_inputs_are_never_silently_coerced(value):
    with pytest.raises((ValueError,TypeError)):
        pack(value)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),object(),{1:'invalid key'}])
def test_decoder_also_rejects_malformed_non_json_payloads(value):
    with pytest.raises(ValueError):
        unpack(dict(encoding=ENCODING,shared_values={},payload=value))
    with pytest.raises(ValueError):
        unpack(dict(encoding=ENCODING,shared_values={'v0':value},payload={REFERENCE:'v0'}))
