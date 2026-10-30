import copy
import hashlib
import json

import pytest

from sdd.cli_agent import build_prompt
from sdd.consistency import SYSTEM, batches, request, schema, wire_payload
from sdd.consistency_sources import canonicalize, citation_refs
from sdd.facts.model import KnowledgeModel


def record(text, *, file='device.cpp', line=1):
    return dict(status='available', commit='a'*40, file=file, line=line,
                text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


def test_source_contract_and_unexecuted_callback_plan_keep_distinct_kinds_in_both_languages(tmp_cfg):
    from sdd.evidence import _paragraphs
    from sdd.site_markdown import _render
    from sdd.site_localization import display_strings
    answers = [
        dict(text='요청 완료 함수는 관리자 스레드에서 호출해야 합니다.', evidence=['proof'], kind='behavior'),
        dict(text='요청 콜백 진입과 실행 스레드를 기록할 계획이며 아직 실행하지 않았습니다.',
             evidence=['proof'], kind='limitation'),
    ]
    body = '\n\n'.join(_paragraphs([(a['kind'], a['text'], []) for a in answers]))
    tmp_cfg.sdd_dir.mkdir(parents=True)
    (tmp_cfg.sdd_dir/'primary.md').write_text('---\nsource_commit: '+'a'*40
        +'\nsection: doc\ngenerated_design: '+json.dumps(dict(answers={'q': answers}), ensure_ascii=False)
        +'\n---\n\n'+body, encoding='utf-8')
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={
        'doc/q/proof': record('This function shall be called from the manager thread.')})
    content, _, _ = _render(body, 'primary.md', {'primary.md'}, model, '', 'a'*40)
    keys = display_strings(content)
    assert len(keys) == 2  # The unexecuted plan is never merged into the source contract.
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps({'strings': {key: 'Contract.' if '호출해야' in key else
        'Execution check: Record callback entry and thread; this plan has not been executed.'
        for key in keys}}), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = str(catalog)
    payload = request(tmp_cfg, model, dict(id='c', question='Who completes?', primary='primary.md',
        documents=['primary.md'], match='요청'))
    for index, expected in enumerate(('behavior', 'limitation')):
        source = payload['claims'][f'primary.md/q/{index}']
        assert source['statement_kinds'] == [expected]
        displayed = [c for k,c in payload['claims'].items() if k.startswith('catalog/')
                     and f'primary.md/q/{index}' in c['origin_claims']]
        assert {c['language'] for c in displayed} == {'ko', 'en'}
        assert all(c['statement_kinds'] == [expected] for c in displayed)


def test_recovered_topic_mapping_order_preserves_exact_audit_requests(tmp_cfg):
    """A partial resume can append one answer topic after its unchanged peers."""
    from sdd.call_records import canonical_request_hash
    topics = {name: [dict(text=f'요청 완료 계약 {name} {i}를 보존합니다.', evidence=['proof'])
                     for i in range(4)] for name in ('alpha', 'zeta')}
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={
        f'doc/{name}/proof': record(f'void {name}() {{ complete(); }}', file=name+'.cpp')
        for name in topics})
    tmp_cfg.sdd_dir.mkdir(parents=True)
    path = tmp_cfg.sdd_dir/'primary.md'
    body = '\n\n'.join(a['text'] for answers in topics.values() for a in answers)
    group = dict(id='completion', question='Who completes?', primary='primary.md', documents=['primary.md'], match='요청')

    def requests(order):
        artifact = dict(answers={name: topics[name] for name in order})
        path.write_text('---\nsource_commit: '+'a'*40+'\nsection: doc\ngenerated_design: '
                        +json.dumps(artifact, ensure_ascii=False)+'\n---\n\n'+body, encoding='utf-8')
        payload = request(tmp_cfg, model, group)
        return [dict(system=SYSTEM, user=json.dumps(wire_payload(batch), ensure_ascii=False, separators=(',', ':')),
                     response_schema=schema(batch)) for batch in batches(payload)]

    before = requests(['zeta', 'alpha'])
    after = requests(['alpha', 'zeta'])
    assert len(before) > 1  # Includes primary peers and schema enums across batches.
    assert before == after
    assert [canonical_request_hash(r) for r in before] == [canonical_request_hash(r) for r in after]
    topics['alpha'][0]['text'] += ' 호출 주체가 달라집니다.'
    assert requests(['alpha', 'zeta']) != after


@pytest.mark.parametrize('same', [False, True])
def test_selected_group_sources_supplement_direct_claim_and_displayed_translation_proof(tmp_cfg, same):
    from sdd.site_markdown import _render
    from sdd.site_localization import display_strings
    text = '요청을 완료하는 호출자는 `completeRequest()`를 명시적으로 호출해야 합니다.'
    artifact = dict(answers={'q': [dict(text=text, evidence=['direct'])]})
    tmp_cfg.sdd_dir.mkdir(parents=True)
    (tmp_cfg.sdd_dir/'primary.md').write_text('---\nsource_commit: '+ 'a'*40
        + '\nsection: doc\ngenerated_design: '+json.dumps(artifact, ensure_ascii=False)+'\n---\n\n'+text, encoding='utf-8')
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={
        'doc/q/direct': record('void completeRequest() { callback(); }'),
        'shared/x/selected': record('void completeRequest() { callback(); }' if same else 'void stop() { cancel(); }')})
    rendered, _, _ = _render(text, 'primary.md', {'primary.md'}, model, '', 'a'*40)
    key, = display_strings(rendered)
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps({'strings': {key: 'The caller must explicitly invoke {{1}} to complete the request.'}}), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = str(catalog)
    payload = request(tmp_cfg, model, dict(id='c', question='Who completes?', primary='primary.md',
        documents=['primary.md'], match='요청', evidence=['shared/x/selected']))
    assert len(payload['sources']) == (1 if same else 2)
    assert payload['source_aliases']['doc/q/direct'] in payload['sources']
    for claim in payload['claims'].values():
        assert claim['evidence'] == [payload['source_aliases']['doc/q/direct']]
    assert any(claim['language']=='en' for claim in payload['claims'].values())
    model.evidence['doc/q/direct']['sha256'] = 'tampered'
    with pytest.raises(ValueError, match='Invalid consistency source'):
        request(tmp_cfg, model, dict(id='c', primary='primary.md', documents=['primary.md'],
            match='요청', evidence=['shared/x/selected']))


def test_canonical_sources_need_identical_bytes_location_and_revision():
    claims = {'a': {'evidence': ['x', 'y', 'z']}}
    sources = {name: dict(file='f.cpp', line=line, sha256='digest', text=text)
               for name, line, text in [('x', 1, 'same'), ('y', 2, 'same'), ('z', 1, 'other')]}
    actual, shared, aliases = canonicalize(claims, sources, ['x'])
    assert len(actual) == 3 and claims['a']['evidence'] == ['x', 'y', 'z']


def test_joined_display_unit_keeps_unmatched_clause_proof_and_code_identity(tmp_cfg):
    from sdd.site_markdown import _render
    from sdd.site_localization import display_strings
    first = '요청을 완료하는 호출자는 `completeRequest()`를 명시적으로 호출해야 합니다.'
    second = '기록된 제어값은 `foo.clear()`로 초기화하고 컬렉션 내용을 비웁니다.'
    other = second.replace('foo.clear()', 'bar.clear()')
    artifact = dict(answers={'q': [dict(text=text, evidence=[sid])
        for text, sid in [(first, 'a'), (second, 'b'), (other, 'c')]]})
    tmp_cfg.sdd_dir.mkdir(parents=True)
    body = first+' '+second
    (tmp_cfg.sdd_dir/'primary.md').write_text('---\nsource_commit: '+'a'*40
        +'\nsection: doc\ngenerated_design: '+json.dumps(artifact, ensure_ascii=False)+'\n---\n\n'+body, encoding='utf-8')
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={
        'doc/q/'+sid: record(text, file=sid+'.cpp') for sid, text in
        [('a', 'void completeRequest() { done(); }'), ('b', 'void reset() { foo.clear(); }'), ('c', 'void reset() { bar.clear(); }')]})
    rendered, _, _ = _render(body, 'primary.md', {'primary.md'}, model, '', 'a'*40)
    key, = display_strings(rendered)
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps({'strings': {key: 'The caller must invoke {{1}}. Values are cleared with {{3}}.'}}), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = str(catalog)
    actual = request(tmp_cfg, model, dict(id='c', primary='primary.md', documents=['primary.md'], match='요청'))
    for claim_id, claim in actual['claims'].items():
        if claim_id.startswith('catalog/'):
            assert set(claim['evidence']) == {'doc/q/a', 'doc/q/b'}
    assert 'doc/q/c' not in actual['sources']


def payload():
    claims = {'p': dict(document='primary.md', text='Primary contract', evidence=['primary'])}
    claims.update({f'c{i}': dict(document='peer.md', text='Contract '+str(i), evidence=[f's{i}']) for i in range(6)})
    sources = {name: dict(file=name+'.cpp', line=1, text=name+' '+('source '*40), sha256=name)
               for name in ['primary', 'shared', *[f's{i}' for i in range(6)]]}
    return dict(contract=dict(primary='primary.md'), source_commit='a'*40, claims=claims,
                sources=sources, shared_sources=['shared'], source_aliases={'alias': 'primary'})


def test_batches_preserve_direct_and_all_primary_sources_and_fit_exact_cli_prompt():
    data = payload()
    singles = list(batches(data, size=1))
    budget = max(len(build_prompt(SYSTEM, json.dumps(wire_payload(part), ensure_ascii=False,
                     separators=(',', ':')), schema(part))) for part in singles)
    actual = list(batches(data, max_input_chars=budget))
    assert len(actual) > 1
    assert [key for part in actual for key in part['claims']] == list(data['claims'])
    for part in actual:
        assert 'p' in part['claims'] or 'p' in part['peer_claims']
        assert {'shared', 'primary'} <= part['sources'].keys()
        assert 'source_aliases' not in part
        assert all(sid in part['sources'] for row in [*part['claims'].values(), *part['peer_claims'].values()]
                   for sid in row['evidence'])
        wire = wire_payload(part)
        assert set(wire['claims']) == set(part['claims'])
        assert set(wire['peer_claims']) == set(part['peer_claims'])
        assert all(wire['sources'][key]['text'] == value['text'] and
                   wire['sources'][key]['file'] == value['file'] and
                   wire['sources'][key]['line'] == value['line'] for key, value in part['sources'].items())
        assert len(build_prompt(SYSTEM, json.dumps(wire, ensure_ascii=False, separators=(',', ':')), schema(part))) <= budget
    with pytest.raises(ValueError, match='full target, primary context and sources'):
        list(batches(data, max_input_chars=1))
    bad = copy.deepcopy(data)
    del bad['sources']['s1']
    with pytest.raises(ValueError, match='missing direct evidence'):
        list(batches(bad))


def test_existing_citation_resolves_verified_context_and_keeps_unresolved_citations_visible():
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={
        'broad': record('a\nb\nc\nd\ne'), 'narrow': record('b\nc', line=2),
        'unavailable': dict(status='unavailable', file='device.cpp'),
        'unrelated-malformed': dict(status='available', file='device.cpp', line=100, text=None)})
    assert citation_refs(model, '분기 근거는 `device.cpp:2`와 `missing.cpp:1`입니다.') == ['narrow']
    model.evidence['narrow']['commit'] = 'b'*40
    with pytest.raises(ValueError, match='Invalid consistency source'):
        citation_refs(model, '근거 `device.cpp:2`입니다.')


def test_visible_short_statements_need_complete_sentence_boundaries():
    from sdd.consistency_sources import contains_statement
    assert contains_statement('완료합니다.', '완료합니다.')
    assert contains_statement('완료합니다.', '준비합니다. 완료합니다. 반환합니다.')
    assert not contains_statement('완료합니다.', '요청을 완료합니다.')
    assert not contains_statement('', '완료합니다.')


def test_short_displayed_contract_translation_is_not_omitted(tmp_cfg):
    text = '완료합니다.'
    artifact = dict(answers={'q': [dict(text=text, evidence=['a'])]})
    tmp_cfg.sdd_dir.mkdir(parents=True)
    (tmp_cfg.sdd_dir/'primary.md').write_text('---\nsource_commit: '+'a'*40
        +'\nsection: doc\ngenerated_design: '+json.dumps(artifact, ensure_ascii=False)+'\n---\n\n'+text, encoding='utf-8')
    model = KnowledgeModel(meta={'source_commit': 'a'*40}, evidence={'doc/q/a': record('The caller completes the request.')})
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps({'strings': {text: 'Completion is prohibited.'}}), encoding='utf-8')
    tmp_cfg.raw.setdefault('site', {})['english_catalog'] = str(catalog)
    actual = request(tmp_cfg, model, dict(id='short', primary='primary.md', documents=['primary.md'], match='완료'))
    assert any(claim['language']=='en' and claim['text']=='Completion is prohibited.' for claim in actual['claims'].values())
