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
    def run(argv, **kwargs):
        payload = json.loads(kwargs['prompt'].split('<user>\n',1)[1].split('\n</user>',1)[0])
        calls.append(payload)
        findings = [dict(claim_id=key, claim_quote=value['text'], peers=[], status='compatible',
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
