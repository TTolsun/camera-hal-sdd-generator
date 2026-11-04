import copy
import json
from types import SimpleNamespace
import pytest
from sdd.translation_repair import repair


class Writer:
    def __init__(self,value):self.value=value;self.request=None;self.calls=[]
    def chat(self,system,user,**kwargs):
        self.request=json.JSONDecoder().raw_decode(user)[0];self.calls.append(user)
        return json.dumps(self.value.pop(0) if isinstance(self.value,list) else self.value)


def cfg(kind='cli'):
    return SimpleNamespace(agent=SimpleNamespace(kind=kind,model='selected-model'))


def test_repair_preserves_source_and_catalog_and_supplies_actual_feedback():
    catalog={'strings':{'{{0}}를 확인하세요.':'Check {{0}}.'}}
    before=copy.deepcopy(catalog);writer=Writer({'translations':{'0':'Inspect {{0}}.'}})
    assert repair(cfg(),catalog,{'{{0}}를 확인하세요.':'Preserve the instruction.'},writer)=={'{{0}}를 확인하세요.':'Inspect {{0}}.'}
    assert catalog==before and writer.request['0']['review_finding']=='Preserve the instruction.'


@pytest.mark.parametrize('value',[
    {'translations':{}},
    {'translations':{'0':'Inspect it.'}},
    {'translations':{'0':'Inspect {{0}} and {{0}}.'}},
    {'translations':{'0':'확인하세요.'}},
])
def test_repair_rejects_missing_ids_or_changed_placeholder_counts(value):
    with pytest.raises(ValueError):repair(cfg(),{'strings':{'{{0}}를 확인하세요.':'Check {{0}}.'}},{'{{0}}를 확인하세요.':'Keep subject'},Writer(value))


def test_repair_rejects_non_cli_and_unknown_feedback_before_call():
    writer=Writer({})
    for configuration,findings in [(cfg('response-bundle'),{'s':'Reason'}),(cfg(),{'unknown':'Reason'}),(cfg(),{'s':''}),(cfg(),{})]:
        with pytest.raises(ValueError):repair(configuration,{'strings':{'s':'old'}},findings,writer)
    assert writer.request is None


def test_validation_retry_is_a_new_call_and_preserves_failure_feedback():
    writer=Writer([{'translations':{'0':'Inspect {{0}} and {{0}}.'}}, {'translations':{'0':'Inspect {{0}}.'}}])
    assert repair(cfg(),{'strings':{'{{0}}를 확인하세요.':'Check {{0}}.'}},{'{{0}}를 확인하세요.':'Keep instruction'},writer)=={'{{0}}를 확인하세요.':'Inspect {{0}}.'}
    assert len(writer.calls)==2 and 'unexpected or repeated' in writer.calls[1]
