"""Cross-document fixtures are separate from real published manuscripts."""
import copy
import json

import pytest

from sdd.consistency import validate


@pytest.fixture
def contract_case():
    source = 'Normal last-buffer completion does not complete the request. During stop all tracked requests complete.'
    payload = dict(claims={
        'vendor': dict(text='During stop, all tracked requests complete.'),
        'developer': dict(text='The last buffer does not automatically complete a request.')},
        sources={'source': dict(file='handler.cpp', line=1, text=source)})
    findings = [dict(claim_id=key, claim_quote=value['text'], peers=[other for other in payload['claims'] if other != key],
                     status='compatible', condition='stop' if key == 'vendor' else 'normal processing',
                     actor='pipeline handler', timing='during stop' if key == 'vendor' else 'last buffer completion',
                     scope='tracked requests' if key == 'vendor' else 'request', reason='Different conditions coexist.',
                     sources=[dict(source_id='source', source_quote=source)]) for key, value in payload['claims'].items()]
    return payload, findings


def test_consistency_preserves_condition_dimensions_and_every_claim(contract_case):
    payload, findings = contract_case
    assert validate(payload, json.dumps(dict(findings=findings))) == findings
    assert findings[0]['condition'] != findings[1]['condition']


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'quote', 'source', 'peer', 'condition', 'unbacked'])
def test_consistency_malformed_or_unbacked_reviews_fail(contract_case, change):
    payload, findings = contract_case
    if change == 'missing':
        findings.pop()
    elif change == 'duplicate':
        findings[1] = copy.deepcopy(findings[0])
    elif change == 'quote':
        findings[0]['claim_quote'] = 'rewritten claim'
    elif change == 'source':
        findings[0]['sources'][0]['source_quote'] = 'invented guarantee'
    elif change == 'peer':
        findings[0]['peers'] = ['unknown']
    elif change == 'condition':
        findings[0]['condition'] = ''
    else:
        findings[0]['status'] = 'contradiction'
        findings[0]['sources'] = []
    with pytest.raises(ValueError):
        validate(payload, json.dumps(dict(findings=findings)))


def test_uncertain_assessment_is_exposed_without_claiming_source_support(contract_case):
    payload, findings = contract_case
    findings[0].update(status='insufficient-evidence', sources=[], condition='not established')
    assert validate(payload, json.dumps(dict(findings=findings)))[0]['status'] == 'insufficient-evidence'
