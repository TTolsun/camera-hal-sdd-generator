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
    findings = [dict(claim_id=key, peers=[other for other in payload['claims'] if other != key],
                     status='compatible', condition='stop' if key == 'vendor' else 'normal processing',
                     actor='pipeline handler', timing='during stop' if key == 'vendor' else 'last buffer completion',
                     scope='tracked requests' if key == 'vendor' else 'request', reason='Different conditions coexist.',
                     sources=[dict(source_id='source')]) for key, value in payload['claims'].items()]
    return payload, findings


def test_consistency_preserves_condition_dimensions_and_every_claim(contract_case):
    payload, findings = contract_case
    result = validate(payload, json.dumps(dict(findings=findings)))
    expected = copy.deepcopy(findings)
    for row in expected:
        row['claim_quote'] = payload['claims'][row['claim_id']]['text']
        for ref in row['sources']:
            ref['source_quote'] = payload['sources'][ref['source_id']]['text']
    assert result == expected
    assert findings[0]['condition'] != findings[1]['condition']


def test_canonical_report_quote_cannot_be_rewritten(contract_case):
    payload, findings = contract_case
    assembled = validate(payload, json.dumps(dict(findings=findings)))
    assert validate(payload, json.dumps(dict(findings=assembled)), assembled=True) == assembled
    assembled[0]['claim_quote'] = 'changed original claim'
    with pytest.raises(ValueError, match='claim quote changed'):
        validate(payload, json.dumps(dict(findings=assembled)), assembled=True)


def test_canonical_source_context_cannot_be_replaced_by_a_literal_subset(contract_case):
    payload, findings = contract_case
    assembled = validate(payload, json.dumps(dict(findings=findings)))
    assembled[0]['sources'][0]['source_quote'] = payload['sources']['source']['text'][:30]
    with pytest.raises(ValueError, match='source quote'):
        validate(payload, json.dumps(dict(findings=assembled)), assembled=True)


def test_all_primary_peers_remain_visible_across_batches():
    from sdd.consistency import batches
    claims = {f'p{i}': dict(document='primary.md', text=f'Contract {i}') for i in range(15)}
    payload = dict(contract=dict(primary='primary.md'), claims=claims, sources={})
    for batch in batches(payload):
        assert set(batch['claims']) | set(batch['peer_claims']) == set(claims)


def test_displayed_translation_restores_identifiers_and_translated_link_text():
    from sdd.site_localization import display_pairs
    document = '<p>요청 완료는 <code>Request::complete()</code> 이후 <a href="callback.html">콜백</a>을 반환합니다.</p>'
    key = '요청 완료는 {{1}} 이후 {{3}}을 반환합니다.'
    pairs = display_pairs(document, {key: '{{3}} returns after {{1}} completes the request.', '콜백': 'callback'})
    pair = next(row for row in pairs if row['key'] == key)
    assert pair['source'] == '요청 완료는 Request::complete() 이후 콜백을 반환합니다.'
    assert pair['translated'] == 'callback returns after Request::complete() completes the request.'


def test_contract_translations_use_current_document_units_only(tmp_cfg):
    from sdd.consistency import request
    from sdd.export_site import _render
    from sdd.facts.model import KnowledgeModel
    from sdd.site_localization import display_strings
    revision = 'a'*40
    model = KnowledgeModel(meta={'source_commit': revision})
    tmp_cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
    body = '요청 완료를 처리하는 책임 주체는 `Request::complete()` 함수를 호출합니다.'
    (tmp_cfg.sdd_dir/'primary.md').write_text(f'---\nsource_commit: {revision}\n---\n\n{body}', encoding='utf-8')
    content, _, _ = _render(body, 'primary.md', {'primary.md'}, model, '', revision)
    key, = display_strings(content)
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps(dict(strings={key: 'The request completion actor calls {{1}}.',
        body+' This unused catalog unit is stale.': 'Always returns a different request.'})), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = str(catalog)
    payload = request(tmp_cfg, model, dict(id='completion', primary='primary.md', documents=['primary.md'], match='요청'))
    english = [claim for claim in payload['claims'].values() if claim['language']=='en']
    assert len(english) == 1
    assert english[0]['text'] == 'The request completion actor calls Request::complete().'
    assert english[0]['document'] == 'primary.md'


def test_no_sources_has_a_valid_empty_reference_schema_and_cannot_support_definite_verdicts(contract_case):
    from sdd.consistency import schema
    payload, findings = contract_case
    payload['sources'] = {}
    for row in findings:
        row.update(status='insufficient-evidence', sources=[])
    assert schema(payload)['properties']['findings']['items']['properties']['sources'] == dict(type='array', maxItems=0)
    assert validate(payload, json.dumps(dict(findings=findings)))[0]['status'] == 'insufficient-evidence'
    findings[0]['status'] = 'compatible'
    with pytest.raises(ValueError, match='requires source'):
        validate(payload, json.dumps(dict(findings=findings)))


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


def test_peer_claims_cannot_hide_missing_primary_contract(tmp_cfg):
    from sdd.consistency import request
    from sdd.facts.model import KnowledgeModel
    revision = 'a'*40
    model = KnowledgeModel(meta={'source_commit': revision})
    tmp_cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
    for name, text in [('primary.md', 'Unrelated introduction.'), ('peer.md', 'The caller completes a request.')]:
        (tmp_cfg.sdd_dir/name).write_text(f'---\nsource_commit: {revision}\n---\n\n{text}', encoding='utf-8')
    group = dict(id='completion', primary='primary.md', documents=['primary.md', 'peer.md'], match='request')
    with pytest.raises(ValueError, match='No primary document contract claims'):
        request(tmp_cfg, model, group)
    (tmp_cfg.sdd_dir/'primary.md').write_text(f'---\nsource_commit: {revision}\n---\n\nA request completes.', encoding='utf-8')
    payload = request(tmp_cfg, model, group)
    assert {claim['document'] for claim in payload['claims'].values()} == {'primary.md', 'peer.md'}


def test_audit_requires_real_archives_and_rejects_stale_or_tampered_report(tmp_cfg, monkeypatch):
    import hashlib
    import subprocess
    import yaml
    from sdd.config import AgentConfig
    from sdd.consistency import audit, enforce
    from sdd.facts.model import KnowledgeModel
    from sdd.llm import Agent
    tmp_cfg.agent = AgentConfig(kind='cli', runner='claude', model='fixture-model', max_input_chars=40000)
    tmp_cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
    revision = 'a'*40
    path = tmp_cfg.sdd_dir/'primary.md'
    path.write_text(f'---\nsource_commit: {revision}\n---\n\nThe caller completes a request.', encoding='utf-8')
    config = tmp_cfg.root/'contracts.yaml'
    config.write_text(yaml.safe_dump(dict(contracts=[dict(id='completion', question='Who completes it?',
        primary='primary.md', documents=['primary.md'], match='request', evidence=['s/t/source'])])), encoding='utf-8')
    tmp_cfg.paths['consistency_file'] = config
    source = 'The caller shall explicitly complete a request.'
    model = KnowledgeModel(meta=dict(source_commit=revision), evidence={'s/t/source': dict(
        text=source, sha256=hashlib.sha256(source.encode()).hexdigest(), commit=revision, file='device.cpp', line=5)})
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])
    calls = []
    verdict = {'value': 'compatible'}
    def run(argv, **kwargs):
        payload = json.loads(kwargs['prompt'].split('<user>\n',1)[1].split('\n</user>',1)[0])
        calls.append(payload)
        findings = [dict(claim_id=key, peers=[], status=verdict['value'],
                         condition='explicit completion', actor='caller', timing='during completion',
                         scope='the request', reason='Fixture source matches.', sources=[dict(source_id='s/t/source')])
                    for key,value in payload['claims'].items()]
        return subprocess.CompletedProcess(argv,0,json.dumps(dict(subtype='success', is_error=False,
            structured_output=dict(findings=findings))), '')
    monkeypatch.setattr('sdd.cli_agent.run', run)
    def agent():return Agent(tmp_cfg.agent, tmp_cfg.build_dir/'prompts')
    report = audit(tmp_cfg, model, agent())
    assert report['status']=='passed' and report['human_review']=='pending'
    enforce(tmp_cfg, model)
    audit(tmp_cfg, model, agent())
    assert len(calls)==1  # Repeat build/review reuses verified exact receipts.
    report['contracts'][0]['findings'][0]['reason']='manually changed verdict'
    report_path=tmp_cfg.build_dir/'consistency-review.json'
    report_path.write_text(json.dumps(report),encoding='utf-8')
    with pytest.raises(ValueError, match='differs'):
        enforce(tmp_cfg, model)
    audit(tmp_cfg, model, agent())
    path.write_text(path.read_text(encoding='utf-8')+' Changed request contract.',encoding='utf-8')
    with pytest.raises(ValueError, match='Stale'):
        enforce(tmp_cfg, model)
    verdict['value'] = 'ambiguous'
    tmp_cfg.agent.model = 'fixture-uncertain-model'
    uncertain = audit(tmp_cfg, model, agent())
    assert len(uncertain['unresolved']) == 1
    hidden = copy.deepcopy(uncertain)
    hidden['unresolved'] = []
    report_path.write_text(json.dumps(hidden), encoding='utf-8')
    with pytest.raises(ValueError, match='unresolved'):
        enforce(tmp_cfg, model)
    hidden = copy.deepcopy(uncertain)
    hidden['human_review'] = 'approved'
    report_path.write_text(json.dumps(hidden), encoding='utf-8')
    with pytest.raises(ValueError, match='metadata'):
        enforce(tmp_cfg, model)
    verdict['value'] = 'contradiction'
    tmp_cfg.agent.model = 'fixture-contradiction-model'
    failed = audit(tmp_cfg, model, agent())
    assert failed['status'] == 'failed'
    failed['status'] = 'passed'  # Editing only the flag must never hide the real verdict.
    report_path.write_text(json.dumps(failed), encoding='utf-8')
    with pytest.raises(ValueError, match='contradiction'):
        enforce(tmp_cfg, model)
