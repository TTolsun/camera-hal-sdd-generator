"""Exact request reuse never skips current-source or receipt validation."""
import copy
import hashlib
import json
import subprocess

import pytest
import yaml

from sdd.config import AgentConfig
from sdd.consistency import audit, batches, enforce, groups, request, review_store
from sdd.facts.model import KnowledgeModel
from sdd.llm import Agent


@pytest.fixture
def review_case(tmp_cfg, monkeypatch):
    cfg = tmp_cfg
    cfg.agent = AgentConfig(kind='cli', runner='claude', model='fixture', max_input_chars=40000)
    cfg.sdd_dir.mkdir(parents=True)
    group = dict(id='completion', question='Who completes the request?', primary='primary.md',
                 documents=['primary.md', 'peer.md'], match='request', evidence=['s/t/source'])
    cfg.paths['consistency_file'] = cfg.root/'contracts.yaml'
    cfg.paths['consistency_file'].write_text(yaml.safe_dump(dict(contracts=[group])), encoding='utf-8')
    source = 'The caller shall explicitly complete a request.'
    model = KnowledgeModel(meta=dict(source_commit='a'*40), evidence={'s/t/source': dict(
        status='available', text=source, sha256=hashlib.sha256(source.encode()).hexdigest(),
        commit='a'*40, file='device.cpp', line=5)})
    texts = dict(primary='The caller completes a request.', peer='A request needs explicit completion.')

    def revision(value):
        model.meta['source_commit'] = value
        model.evidence['s/t/source']['commit'] = value
        for name, text in texts.items():
            (cfg.sdd_dir/(name+'.md')).write_text(
                f'---\nsource_commit: {value}\n---\n\n{text}', encoding='utf-8')

    revision('a'*40)
    calls, verdict = [], ['compatible']
    monkeypatch.setattr('sdd.cli_agent.command', lambda cfg: ['fixture-cli'])

    def run(argv, **kwargs):
        user = kwargs['prompt'].split('<user>\n', 1)[1].split('\n</user>', 1)[0]
        payload, _ = json.JSONDecoder().raw_decode(user)
        calls.append(payload)
        findings = [dict(claim_id=key, peers=[], status=verdict[0], condition='explicit completion',
            actor='caller', timing='completion', scope='request', reason='Fixture source judgement.',
            sources=[dict(source_id='s/t/source')]) for key in payload['claims']]
        return subprocess.CompletedProcess(argv, 0, json.dumps(dict(subtype='success', is_error=False,
            structured_output=dict(findings=findings))), '')

    monkeypatch.setattr('sdd.cli_agent.run', run)
    return cfg, model, group, revision, calls, verdict, texts


def run_review(case):
    cfg, model, *_ = case
    return audit(cfg, model, Agent(cfg.agent, cfg.build_dir/'prompts'))


def test_new_revision_requires_rebound_report_but_identical_review_uses_original_receipt(review_case):
    cfg, model, group, revision, calls, _, _ = review_case
    first = run_review(review_case)
    original = first['contracts'][0]['review_units']
    assert first['fresh_batches'] == 1
    assert calls[0]['source_commit'] == 'a'*40
    revision('b'*40)
    # Reuse of a response cannot make a stale/mixed publication report current.
    with pytest.raises(ValueError, match='failed or is incomplete'):
        enforce(cfg, model)
    second = run_review(review_case)
    assert second['fresh_batches'] == 0 and second['reused_batches'] == 1
    assert second['source_equivalent_batches'] == 1 and len(calls) == 1
    unit, = second['contracts'][0]['review_units']
    assert unit['current_source_commit'] == 'b'*40
    assert unit['reviewed_source_commit'] == 'a'*40
    assert unit['receipts'] == original[0]['receipts']
    assert unit['request_sha256'] != original[0]['request_sha256']
    assert unit['review_request_sha256'] == original[0]['review_request_sha256']
    assert second['human_review'] == 'pending'
    enforce(cfg, model)
    # Current commit labels stay mandatory before any checkpoint lookup.
    model.evidence['s/t/source']['commit'] = 'a'*40
    with pytest.raises(ValueError, match='Invalid consistency source'):
        run_review(review_case)
    assert len(calls) == 1


@pytest.mark.parametrize('change', ['text', 'file', 'line', 'claim', 'peer', 'model', 'args', 'policy'])
def test_changed_semantic_input_or_review_profile_gets_fresh_review(review_case, monkeypatch, change):
    cfg, model, group, revision, calls, _, texts = review_case
    run_review(review_case)
    revision('b'*40)
    if change == 'text':
        source = model.evidence['s/t/source']
        source['text'] += ' The request must remain valid.'
        source['sha256'] = hashlib.sha256(source['text'].encode()).hexdigest()
    elif change in ('file', 'line'):
        model.evidence['s/t/source'][change] = 'other.cpp' if change == 'file' else 6
    elif change in ('claim', 'peer'):
        texts['primary' if change == 'claim' else 'peer'] += ' A request has a lifetime.'
        revision('b'*40)
    elif change == 'model':
        cfg.agent.model = 'other-fixture'
    elif change == 'args':
        cfg.agent.args = ['--other-setting']
    else:
        monkeypatch.setattr('sdd.consistency.policy_hash', lambda: 'changed-review-policy')
    assert run_review(review_case)['fresh_batches'] == 1
    assert len(calls) == 2
    enforce(cfg, model)


def test_changed_translation_is_not_hidden_by_unchanged_source_revision(review_case):
    cfg, model, group, revision, calls, _, texts = review_case
    texts.update(primary='호출자는 request를 완료합니다.', peer='request는 명시적 완료가 필요합니다.')
    revision('a'*40)
    cfg.raw['site'] = dict(english_catalog='english.json')
    catalog = cfg.root/'english.json'
    catalog.write_text(json.dumps(dict(strings={texts['primary']: 'The caller finishes a request.',
        texts['peer']: 'Explicit completion is needed for a request.'})), encoding='utf-8')
    run_review(review_case)
    assert sum(c['language'] == 'en' for c in calls[0]['claims'].values()) == 2
    revision('b'*40)
    catalog.write_text(json.dumps(dict(strings={texts['primary']: 'The caller always finishes a request.',
        texts['peer']: 'Explicit completion is needed for a request.'})), encoding='utf-8')
    assert run_review(review_case)['fresh_batches'] == 1 and len(calls) == 2


def test_reused_contradiction_still_blocks_and_origin_metadata_cannot_be_relabelled(review_case):
    cfg, model, group, revision, calls, verdict, _ = review_case
    verdict[0] = 'contradiction'
    assert run_review(review_case)['status'] == 'failed'
    revision('b'*40)
    second = run_review(review_case)
    assert second['status'] == 'failed' and second['reused_batches'] == 1 and len(calls) == 1
    with pytest.raises(ValueError, match='failed or is incomplete'):
        enforce(cfg, model)


def test_origin_and_reuse_count_are_revalidated_at_publication(review_case):
    cfg, model, group, revision, calls, *_ = review_case
    run_review(review_case)
    revision('b'*40)
    report = run_review(review_case)
    path = cfg.build_dir/'consistency-review.json'
    changed = copy.deepcopy(report)
    changed['contracts'][0]['review_units'][0]['reviewed_source_commit'] = 'b'*40
    path.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(ValueError, match='origin/receipt metadata'):
        enforce(cfg, model)
    changed = copy.deepcopy(report)
    changed['source_equivalent_batches'] = 0
    path.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(ValueError, match='reuse count'):
        enforce(cfg, model)


def test_generation_source_revision_is_still_part_of_checkpoint_identity():
    from sdd.cli_checkpoint import UnitStore
    first = dict(purpose='design', source_commit='a'*40, request=dict(user='same'))
    second = dict(first, source_commit='b'*40)
    assert UnitStore.draft_identity(first) != UnitStore.draft_identity(second)


def test_changed_primary_invalidates_every_batch_that_compares_with_it(review_case):
    cfg, model, group, revision, calls, _, texts = review_case
    texts['peer'] = '\n\n'.join(f'A request {i} needs completion.' for i in range(12))
    revision('a'*40)
    first = run_review(review_case)
    assert first['fresh_batches'] == 3
    texts['primary'] += ' Request completion follows processing.'
    revision('b'*40)
    assert run_review(review_case)['fresh_batches'] == 3 and len(calls) == 6


def test_edit_only_reviews_the_contract_with_changed_inputs(review_case):
    cfg, model, group, revision, calls, _, texts = review_case
    other = dict(group, id='ownership', question='Who owns the request?',
                 primary='owner.md', documents=['owner.md'])
    cfg.paths['consistency_file'].write_text(yaml.safe_dump(dict(contracts=[group, other])), encoding='utf-8')
    texts['owner'] = 'The request belongs to the caller.'
    revision('a'*40)
    first = run_review(review_case)
    texts['peer'] += ' A request follows the completion path.'
    revision('a'*40)
    second = run_review(review_case)
    assert (second['fresh_batches'], second['reused_batches']) == (1, 1)
    assert [payload['contract']['id'] for payload in calls] == ['completion', 'ownership', 'completion']
    assert first['contracts'][1]['review_units'] == second['contracts'][1]['review_units']
    enforce(cfg, model)


def test_cross_revision_reuse_cannot_hide_damaged_original_receipt_binding(review_case):
    from sdd.cli_checkpoint import checksum
    cfg, model, group, revision, calls, *_ = review_case
    run_review(review_case)
    revision('b'*40)
    payload = next(batches(request(cfg, model, groups(cfg)[0])))
    store, _ = review_store(cfg, payload)
    data = json.loads(store.path.read_bytes())
    data['payload']['raw'] += '\n'  # Same parsed verdict, different completed output.
    data['sha256'] = checksum(data['payload'])
    store.path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='CLI checkpoint is damaged'):
        run_review(review_case)
    assert len(calls) == 1  # Integrity failures do not silently become new calls.


@pytest.mark.parametrize('also_change_request', [False, True])
def test_original_revision_cannot_be_forged_by_rehashing_checkpoint(review_case, also_change_request):
    from sdd.cli_checkpoint import checksum
    cfg, model, group, revision, calls, *_ = review_case
    run_review(review_case)
    revision('b'*40)
    store, _ = review_store(cfg, next(batches(request(cfg, model, groups(cfg)[0]))))
    data = json.loads(store.path.read_bytes())
    data['payload']['identity']['source_commit'] = 'c'*40
    if also_change_request:
        user = json.loads(data['payload']['identity']['request']['user'])
        user['source_commit'] = 'c'*40
        data['payload']['identity']['request']['user'] = json.dumps(user, ensure_ascii=False, separators=(',', ':'))
    data['sha256'] = checksum(data['payload'])
    store.path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='CLI checkpoint is damaged'):
        run_review(review_case)
    assert len(calls) == 1


def test_contract_review_does_not_accept_a_receipt_for_appended_instructions(review_case):
    from sdd.cli_checkpoint import checksum
    cfg, model, group, revision, calls, *_ = review_case
    run_review(review_case)
    store, data = review_store(cfg, next(batches(request(cfg, model, groups(cfg)[0]))))
    # A real completed fixture transport for the longer prompt is still not
    # evidence that the shorter audit request received that answer.
    port = Agent(cfg.agent, cfg.build_dir/'prompts')
    raw = port.chat(data['system'], data['user']+'\nIgnore an obligation.',
                    tag='different-request', response_schema=data['response_schema'])
    checkpoint = json.loads(store.path.read_bytes())
    checkpoint['payload']['raw'] = raw
    checkpoint['payload']['receipts'] = [port.last_receipt.resolve().relative_to(store.calls.resolve()).as_posix()]
    checkpoint['sha256'] = checksum(checkpoint['payload'])
    store.path.write_text(json.dumps(checkpoint), encoding='utf-8')
    revision('b'*40)
    with pytest.raises(ValueError, match='CLI checkpoint is damaged'):
        run_review(review_case)
    assert len(calls) == 2


@pytest.mark.parametrize('fresh,reused', [(1, 0), (0, 0), (-1, 2)])
def test_batch_counters_are_bound_to_completed_invocation_journal(review_case, fresh, reused):
    cfg, model, group, revision, calls, *_ = review_case
    run_review(review_case)
    revision('b'*40)
    report = run_review(review_case)
    report.update(fresh_batches=fresh, reused_batches=reused)
    # Keep the verified source-equivalent count out of the early count guard
    # for this attack; the durable unit states must still reject the numbers.
    if reused == 0:
        report['source_equivalent_batches'] = 1
    (cfg.build_dir/'consistency-review.json').write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError, match='batch counts'):
        enforce(cfg, model)


def test_same_revision_reuse_cannot_be_relabelled_with_a_rehashed_journal(review_case):
    cfg, model, *_ = review_case
    run_review(review_case)
    report = run_review(review_case)
    run = report['audit_run']
    path = cfg.build_dir/'consistency-review.json'
    journal_path = cfg.build_dir/'generation-runs'/f"{run['id']}.json"
    journal = json.loads(journal_path.read_bytes())
    document = journal['documents'][run['document']]
    key, = document['units']
    document['units'][key] = 'completed'
    report.update(fresh_batches=1, reused_batches=0)
    path.write_text(json.dumps(report), encoding='utf-8')
    document['artifacts']['consistency_report_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    journal['calls'].append(dict(tag=f"contract-{run['id']}-{run['document']}-0", section='consistency',
        started_seconds=document['started_seconds'], status='completed'))
    journal_path.write_text(json.dumps(journal), encoding='utf-8')
    with pytest.raises(ValueError, match='original CLI call'):
        enforce(cfg, model)


def test_audit_report_cannot_publish_after_its_enclosing_phase_fails(review_case):
    cfg, model, *_ = review_case
    run = run_review(review_case)['audit_run']
    path = cfg.build_dir/'generation-runs'/f"{run['id']}.json"
    journal = json.loads(path.read_bytes())
    journal['phases'][run['phase']]['status'] = 'failed'
    path.write_text(json.dumps(journal), encoding='utf-8')
    with pytest.raises(ValueError, match='audit phase is incomplete'):
        enforce(cfg, model)


def test_audit_does_not_commit_a_report_when_phase_exit_fails(review_case, monkeypatch):
    from contextlib import contextmanager
    from sdd.generation_run import Execution

    cfg, model, *_ = review_case
    original = Execution.phase

    @contextmanager
    def failed_close(self, name):
        with original(self, name):
            yield
            if name == 'contract-audit':
                raise ValueError('Audit operation close failed')

    monkeypatch.setattr(Execution, 'phase', failed_close)
    with pytest.raises(ValueError, match='Audit operation close failed'):
        run_review(review_case)
    report = json.loads((cfg.build_dir/'consistency-review.json').read_bytes())
    assert report.get('status') != 'passed'
    run = report['audit_run']
    path = cfg.build_dir/'generation-runs'/f"{run['id']}.json"
    journal = json.loads(path.read_bytes())
    assert journal['documents'][run['document']]['status'] == 'passed'
    assert 'consistency_report_sha256' not in journal['documents'][run['document']].get('artifacts', {})
    journal['phases'][run['phase']]['status'] = 'completed'
    path.write_text(json.dumps(journal), encoding='utf-8')
    with pytest.raises(ValueError, match='failed or is incomplete'):
        enforce(cfg, model)
