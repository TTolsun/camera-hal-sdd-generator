from pathlib import Path
import importlib.util
import pytest
import json
import hashlib
import base64
import subprocess
import sys
import shutil
import yaml
from types import SimpleNamespace


def _native_verifier():
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/verify_native_calls.py'
    spec=importlib.util.spec_from_file_location('issue252_native_verifier',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _source_auditor():
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/audit.py'
    spec=importlib.util.spec_from_file_location('issue252_source_auditor',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('combined', [False, True])
def test_reader_output_limits_are_scoped_to_exposed_tools(tmp_path, monkeypatch, combined):
    path = Path(__file__).parents[1] / 'examples/libcamera/validation/issue252/run_reader.py'
    spec = importlib.util.spec_from_file_location('issue252_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = tmp_path / 'prompt.txt'
    prompt.write_text('Verify evidence delivery.', encoding='utf-8')
    out = tmp_path / 'run'
    seen = {}

    def transport(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, '{"type":"turn.completed"}\n', '')

    monkeypatch.setattr(module, 'command', lambda profile: ['codex'])
    monkeypatch.setattr(module, 'run', transport)
    args = ['--reader', str(tmp_path / 'reader.py'), '--site', str(tmp_path / 'site'),
            '--prompt', str(prompt), '--out', str(out)]
    if combined:
        args.append('--combined-route')
    assert module.main(args) == 0
    settings = {arg.removeprefix('mcp_servers.public_sdd.').split('=', 1)[0]:
                json.loads(arg.split('=', 1)[1]) for arg in seen['argv']
                if arg.startswith('mcp_servers.public_sdd.')}
    tools = ['route'] if combined else ['route', 'route_source']
    assert settings['enabled_tools'] == tools
    assert {key for key in settings if key.endswith('.output_token_limit')} == {
        f'tools.{tool}.output_token_limit' for tool in tools}
    assert all(settings[f'tools.{tool}.output_token_limit'] == 65536 for tool in tools)
    assert settings['args'][-3:] == [str(tmp_path / name)
                                    for name in ('reader.py', 'site', 'run/navigation.jsonl')]
    assert settings['args'][:-3] == ([] if combined else [str(path.with_name('split_reader.py'))])
    assert not any(arg.startswith('tool_output_token_limit=') for arg in seen['argv'])
    assert seen['prompt'] == 'Verify evidence delivery.'
    assert (out / 'stdout.jsonl').is_file()


@pytest.mark.parametrize('first', ['route', 'route_source'])
def test_split_reader_returns_independent_evidence_without_a_second_archive_call(tmp_path, first):
    reader = tmp_path / 'reader.py'
    reader.write_text(
        "import json, sys\n"
        "calls = 0\n"
        "for line in sys.stdin:\n"
        "    message = json.loads(line)\n"
        "    if message['method'] == 'tools/list':\n"
        "        result = {'tools': [{'name': 'route', 'inputSchema': {'type': 'object'}}]}\n"
        "    else:\n"
        "        assert message['params'] == {'name': 'route', 'arguments': {'question': 'Q2'}}\n"
        "        calls += 1\n"
        "        assert calls == 1\n"
        "        bundle = {'sections': [{'excerpt': '문서'}], 'code_links_opened': ["
        "{'href': 'https://example.com/source.cpp#L42', 'code': '42: finish();'}]}\n"
        "        result = {'content': [{'type': 'text', 'text': json.dumps(bundle)}]}\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)\n",
        encoding='utf-8',
    )
    expected = {'route': {'sections': [{'excerpt': '문서'}]}, 'route_source': {
        'code_links_opened': [{'href': 'https://example.com/source.cpp#L42', 'code': '42: finish();'}]}}
    names = [first, next(name for name in expected if name != first), first]
    messages = [{'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'}]
    messages.extend({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                     'params': {'name': name, 'arguments': {'question': 'Q2'}}}
                    for index, name in enumerate(names, 1))
    path = Path(__file__).parents[1] / 'examples/libcamera/validation/issue252/split_reader.py'
    run = subprocess.run([sys.executable, str(path), str(reader), str(tmp_path), str(tmp_path / 'log')],
                         input='\n'.join(map(json.dumps, messages)).encode(), capture_output=True,
                         timeout=15, check=True)
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    assert [reply['id'] for reply in replies] == list(range(len(messages)))
    assert [tool['name'] for tool in replies[0]['result']['tools']] == ['route', 'route_source']
    for name, reply in zip(names, replies[1:], strict=True):
        assert json.loads(reply['result']['content'][0]['text']) == expected[name]


def test_bilingual_dedup_references_only_unique_exact_source_bytes():
    module=_source_auditor();snippet='return 73;\n'
    windows={'source.cpp':dict(text='before\n'+snippet+'after\n')}
    original='## Question\nA reader condition remains.\n```text\n'+snippet+'```\n```mermaid\nflowchart LR\nA-->B\n```\n'
    text,records=module.deduplicate_source_blocks(original,windows)
    assert len(records)==1 and records[0]['file']=='source.cpp'
    row=records[0]
    assert windows[row['file']]['text'][row['source_start']:row['source_end']]==snippet
    assert row['code_sha256']==hashlib.sha256(snippet.encode()).hexdigest()
    assert 'A reader condition remains.' in text and 'flowchart LR\nA-->B' in text
    assert module.document_items(text)==module.document_items(original)
    assert windows['source.cpp']['text']=='before\n'+snippet+'after\n'


def test_bilingual_dedup_keeps_changed_or_ambiguously_located_excerpt():
    module=_source_auditor();original='```text\nreturn 73;\n```\n'
    for windows in [
        {'a.cpp':dict(text='return 74;\n')},
        {'a.cpp':dict(text='return 73;\nreturn 73;\n')},
        {'a.cpp':dict(text='return 73;\n'),'b.cpp':dict(text='return 73;\n')},
    ]:
        assert module.deduplicate_source_blocks(original,windows)==(original,[])


def test_bilingual_dedup_preserves_real_code_indentation():
    module=_source_auditor();snippet='    return 73;\n'
    original='    ```text\n    '+snippet+'    ```\n'
    _,records=module.deduplicate_source_blocks(original,{'a.cpp':dict(text='before\n'+snippet+'after\n')})
    assert len(records)==1
    assert records[0]['code_sha256']==hashlib.sha256(snippet.encode()).hexdigest()


@pytest.mark.parametrize('language',['mermaid','json','cpp'])
def test_bilingual_dedup_does_not_remove_other_display_blocks(language):
    module=_source_auditor();original='```'+language+'\nreturn 73;\n```\n'
    assert module.deduplicate_source_blocks(original,{'a.cpp':dict(text='return 73;\n')})==(original,[])


def test_bilingual_dedup_keeps_literal_nested_fence():
    module=_source_auditor();original='````md\n```text\nreturn 73;\n```\n````\n'
    assert module.deduplicate_source_blocks(original,{'a.cpp':dict(text='return 73;\n')})==(original,[])


def test_review_resume_only_calls_affected_questions(tmp_cfg, monkeypatch):
    from sdd.config import AgentConfig

    module = _source_auditor()
    run = tmp_cfg.root
    monkeypatch.setattr(module, 'RUN', run)
    monkeypatch.setattr(module, 'load', lambda _: tmp_cfg)
    tmp_cfg.agent = AgentConfig(kind='cli', runner='codex', model='gpt-6.1-terra',
                                command=['fixture-cli', 'exec'], args=['-c', 'model_reasoning_effort="high"'],
                                max_input_chars=100000)
    source = run/'source-windows/source.cpp'
    source.parent.mkdir()
    source.write_bytes(b'return 0;\n')
    scope = yaml.safe_load((module.HERE/'questions.yaml').read_bytes())
    scope['source_windows'] = [dict(file='source.cpp', sha256=hashlib.sha256(source.read_bytes()).hexdigest())]
    scope_file = run/'scope.json'
    scope_file.write_text(json.dumps(scope), encoding='utf-8')
    manuscript = run/'manuscript.md'

    def write_manuscript(stopping='Stopping boundary'):
        body = ''.join(f'\n## {title}\n\n{stopping if key == "stopping" else key}\n'
                       for title, key in module.TOPICS.items())
        manuscript.write_text(f"---\nsource_commit: {scope['source_commit']}\n---\n# Fixture\n{body}", encoding='utf-8')

    calls = []
    monkeypatch.setattr('sdd.cli_agent.command', lambda _: ['fixture-cli', 'exec'])

    def transport(argv, **kwargs):
        user = kwargs['prompt'].split('<user>\n', 1)[1].split('\n</user>', 1)[0]
        payload = json.loads(user)
        questions = payload['scope']['questions']
        calls.append(tuple(q['id'] for q in questions))
        result = dict(status='passed', human_review='pending', findings=[], unreviewed_scope=[],
                      questions=[dict(id=q['id'], answerable=True, answer_location='source:1',
                                      diagnosis_values='status', next_branch='return', change_validation='assert',
                                      source_windows=['source.cpp'], missing=[]) for q in questions],
                      items=[dict(anchor=item['anchor'], visual_status='omitted-with-reason',
                                  question=item['title'], reason='Single fact') for item in payload['expected_h2_h3_items']])
        events = [dict(type='turn.started'), dict(type='item.completed', item=dict(type='agent_message',
                  text=json.dumps(result))), dict(type='turn.completed')]
        return subprocess.CompletedProcess(argv, 0, '\n'.join(map(json.dumps, events)), '')

    monkeypatch.setattr('sdd.cli_agent.run', transport)

    def audit(attempt):
        monkeypatch.setattr(sys, 'argv', ['audit.py', 'accuracy', '--document', str(manuscript), '--attempt', attempt])
        module.main()
        return json.loads((run/f'audits/accuracy-{attempt}/review.json').read_bytes())

    write_manuscript()
    first = audit('01')
    assert (first['fresh_units'], first['reused_units'], len(calls)) == (8, 0, 8)
    unchanged = audit('02')
    assert (unchanged['fresh_units'], unchanged['reused_units'], len(calls)) == (0, 8, 8)
    assert unchanged['review_units']['Q1']['receipts'] == first['review_units']['Q1']['receipts']

    scope['questions'][1]['question'] += ' Check this additional condition.'
    scope_file.write_text(json.dumps(scope), encoding='utf-8')
    assert audit('03')['fresh_units'] == 1 and calls[8:] == [('Q2',)]

    write_manuscript('Stopping boundary changed')
    changed = audit('04')
    assert changed['fresh_units'] == 1 and calls[9:] == [('Q5',)]
    assert len(changed['items']) == len(module.TOPICS)
    assert [q['id'] for q in changed['questions']] == [f'Q{n}' for n in range(1, 8)]


def _historical_import(tmp_path):
    rel='build/prompts/calls/historical/001.receipt.json'
    receipt=tmp_path/rel;receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b'synthetic historical receipt for digest validation only')
    binding=dict(receipt=rel,sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
    manifest=tmp_path/'historical-native-restoration-clarity.json'
    manifest.write_text(json.dumps(dict(schema=2,receipts=[binding])))
    return rel,receipt,manifest


def _trusted_import_maps(tmp_path):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tmp_path.glob('historical-native-restoration-*.json')}


def test_historical_exclusion_verifies_bound_receipt_and_map_bytes(tmp_path):
    rel,_,manifest=_historical_import(tmp_path)
    preserved,maps=_native_verifier().historical_receipts(tmp_path,_trusted_import_maps(tmp_path))
    assert preserved=={rel}
    assert maps==[dict(path=manifest.name,sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())]


@pytest.mark.parametrize('corruption',['replaced','missing'])
def test_historical_exclusion_rejects_changed_or_missing_receipt(tmp_path,corruption):
    _,receipt,_=_historical_import(tmp_path)
    if corruption=='replaced':
        receipt.write_bytes(b'a different receipt at the same path')
    else:
        receipt.unlink()
    with pytest.raises(ValueError,match='missing or changed'):
        _native_verifier().historical_receipts(tmp_path,_trusted_import_maps(tmp_path))


def test_historical_exclusion_rejects_unbound_path_only_map(tmp_path):
    (tmp_path/'historical-native-restoration-navigation.json').write_text(
        json.dumps(dict(receipt_paths=['build/prompts/calls/old/001.receipt.json'])))
    with pytest.raises(ValueError,match='needs receipt digests'):
        _native_verifier().historical_receipts(tmp_path,_trusted_import_maps(tmp_path))


def test_historical_exclusion_rejects_receipt_outside_run(tmp_path):
    (tmp_path/'historical-native-restoration-clarity.json').write_text(json.dumps(dict(
        receipts=[dict(receipt='../outside.receipt.json',sha256='0'*64)])))
    with pytest.raises(ValueError,match='Invalid historical receipt binding'):
        _native_verifier().historical_receipts(tmp_path,_trusted_import_maps(tmp_path))


def test_historical_exclusion_rejects_receipt_and_map_changed_together(tmp_path):
    _,receipt,manifest=_historical_import(tmp_path)
    trusted=_trusted_import_maps(tmp_path)
    receipt.write_bytes(b'replacement with a rewritten import binding')
    data=json.loads(manifest.read_bytes())
    data['receipts'][0]['sha256']=hashlib.sha256(receipt.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Historical import map changed'):
        _native_verifier().historical_receipts(tmp_path,trusted)


def test_historical_exclusion_rejects_removed_import_map(tmp_path):
    _,_,manifest=_historical_import(tmp_path)
    trusted=_trusted_import_maps(tmp_path);manifest.unlink()
    with pytest.raises(ValueError,match='map set changed'):
        _native_verifier().historical_receipts(tmp_path,trusted)


def test_native_verification_rechecks_historical_receipts_before_reporting(tmp_path,monkeypatch):
    _,receipt,_=_historical_import(tmp_path)
    module=_native_verifier()
    monkeypatch.setattr(module,'RUN',tmp_path)
    monkeypatch.setattr(module,'HISTORICAL_IMPORT_MAP_SHA256',_trusted_import_maps(tmp_path))
    monkeypatch.setattr(module,'load',lambda path:SimpleNamespace(agent=object()))
    def changed_records(path):
        receipt.write_bytes(b'replaced while the verifier scans records')
        return []
    monkeypatch.setattr(module,'iter_records',changed_records)
    with pytest.raises(ValueError,match='missing or changed'):
        module.main()
    assert json.loads((tmp_path/'native-call-verification.json').read_bytes())['status']=='failed'


def test_native_verification_does_not_trust_old_timestamp_as_exclusion(tmp_path,monkeypatch):
    calls=tmp_path/'build/prompts/calls';calls.mkdir(parents=True)
    module=_native_verifier()
    monkeypatch.setattr(module,'RUN',tmp_path)
    monkeypatch.setattr(module,'HISTORICAL_IMPORT_MAP_SHA256',{})
    monkeypatch.setattr(module,'load',lambda path:SimpleNamespace(agent=object()))
    record=SimpleNamespace(receipt=dict(completed_at='2020-01-01T00:00:00'),
                           receipt_path=calls/'old.receipt.json')
    monkeypatch.setattr(module,'iter_records',lambda path:[record])
    with pytest.raises(ValueError,match='no digest binding'):
        module.main()
    assert json.loads((tmp_path/'native-call-verification.json').read_bytes())['status']=='failed'


def test_native_verification_failure_archives_and_invalidates_prior_success(tmp_path,monkeypatch):
    _,receipt,_=_historical_import(tmp_path)
    module=_native_verifier()
    monkeypatch.setattr(module,'RUN',tmp_path)
    monkeypatch.setattr(module,'HISTORICAL_IMPORT_MAP_SHA256',_trusted_import_maps(tmp_path))
    monkeypatch.setattr(module,'load',lambda path:SimpleNamespace(agent=object()))
    report=tmp_path/'native-call-verification.json'
    prior=b'{"status":"verified","synthetic_test_fixture":true}\r\n'
    report.write_bytes(prior)
    receipt.write_bytes(b'changed after a prior successful verification')
    with pytest.raises(ValueError,match='missing or changed'):
        module.main()
    latest=json.loads(report.read_bytes())
    assert latest['status']=='failed'
    assert (tmp_path/latest['previous_report']['path']).read_bytes()==prior
    assert latest['previous_report']['sha256']==hashlib.sha256(prior).hexdigest()


def test_native_verification_archive_conflict_preserves_bytes_and_fails_latest(tmp_path,monkeypatch):
    module=_native_verifier();monkeypatch.setattr(module,'RUN',tmp_path)
    prior=b'{"status":"verified","synthetic_test_fixture":true}\r\n'
    report=tmp_path/'native-call-verification.json';report.write_bytes(prior)
    archive=tmp_path/'native-call-verification-history'/(hashlib.sha256(prior).hexdigest()+'.json')
    archive.parent.mkdir();archive.write_bytes(b'conflicting archive evidence')
    with pytest.raises(ValueError,match='archive changed'):
        module.main()
    latest=json.loads(report.read_bytes())
    assert latest['status']=='failed'
    assert base64.b64decode(latest['previous_snapshot']['bytes_base64'])==prior
    assert archive.read_bytes()==b'conflicting archive evidence'


def test_native_verification_rejects_interleaved_attempt_before_it_can_publish(tmp_path,monkeypatch):
    module=_native_verifier();monkeypatch.setattr(module,'RUN',tmp_path)
    report=tmp_path/'native-call-verification.json'
    def outer():
        with pytest.raises(RuntimeError,match='Native call verification'):
            module.main()
        script="""import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('child_verifier',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.RUN=Path(sys.argv[2])
module._verify=lambda:dict(status='verified',calls=[],counts={},historical_calls_excluded=0)
module.main()
"""
        child=subprocess.run([sys.executable,'-X','utf8','-c',script,module.__file__,str(tmp_path)],
                             capture_output=True,text=True,encoding='utf-8',timeout=20)
        assert child.returncode!=0
        assert 'Native call verification' in child.stderr
        assert json.loads(report.read_bytes())['status']=='in-progress'
        return dict(status='verified',calls=[],counts={},historical_calls_excluded=0)
    monkeypatch.setattr(module,'_verify',outer)
    module.main()
    assert json.loads(report.read_bytes())['status']=='verified'
    def later():
        raise ValueError('later attempt fails')
    monkeypatch.setattr(module,'_verify',later)
    with pytest.raises(ValueError,match='later attempt fails'):
        module.main()
    assert json.loads(report.read_bytes())['status']=='failed'

@pytest.mark.parametrize('delimiter',['`','~'])
def test_visual_audit_ignores_shorter_fences_inside_a_longer_code_block(delimiter):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/audit.py'
    spec=importlib.util.spec_from_file_location('issue252_audit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    text='## Before\n'+delimiter*4+'text\n'+delimiter*3+'\n## Inside code\n'+delimiter*4+'not-a-close\n### Also code\n'+delimiter*4+'\n### After\n'
    assert module.document_items(text)==[dict(anchor='item-01',title='Before',level=2),dict(anchor='item-02',title='After',level=3)]


def test_refinement_preserves_concurrently_integrated_lifetime_figures(tmp_path):
    root=Path(__file__).parents[1]
    path=root/'examples/libcamera/validation/issue252/refine.py'
    spec=importlib.util.spec_from_file_location('issue252_refine',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=tmp_path
    module.RUN=tmp_path/'build/issue252/run'
    config=module.RUN/'config';config.mkdir(parents=True)
    example=tmp_path/'examples/libcamera/config';example.mkdir(parents=True)
    for name in ['sections.yaml','visuals.yaml']:
        source=root/'examples/libcamera/config'/name
        shutil.copy2(source,config/name);shutil.copy2(source,example/name)
    audit=module.RUN/'audits/accuracy-01';audit.mkdir(parents=True)
    (audit/'review.json').write_text(json.dumps({'status':'needs-work'}))
    (module.RUN/'public-base-integration.json').write_text('{}')
    baseline=module.RUN.parent/'public/publication/issue214/config';baseline.mkdir(parents=True)
    shutil.copy2(config/'visuals.yaml',baseline/'visuals.yaml')
    def resources(p):
        return [v for v in yaml.safe_load(p.read_bytes())['sections']['request-lifecycle']
                if v.get('topic')=='resources']
    expected=resources(example/'visuals.yaml')
    assert {'completed-but-not-returned','completion-notification-order','completion-change-checks'} <= {v['id'] for v in expected}
    for _ in range(2):
        module.main()
        assert resources(example/'visuals.yaml')==expected
        assert resources(config/'visuals.yaml')==expected


@pytest.mark.parametrize('eol',['\n','\r\n'])
def test_visual_metadata_revalidation_preserves_body_and_historical_aliases(eol):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/revalidate_visuals.py'
    spec=importlib.util.spec_from_file_location('issue252_visual_metadata',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    header='---\nagent: cli/claude/historical\ngenerated_visuals: &original\n  schema: 1\n  records: {old: {model: historical}}\nhistorical_graph_metadata: *original\n---\n'
    body='# Unchanged\n\n```cpp\nint old_value = 0;\n```\n'.replace('\n',eol).encode()
    original=header.replace('\n',eol).encode()+body
    artifact={'schema':1,'records':{'old':{'model':'historical','revalidated':True}}}
    updated=module.replace_visual_metadata(original,artifact)
    assert updated.endswith(body)
    old_meta,_=module.split_frontmatter(original.decode().replace('\r\n','\n'))
    new_meta,_=module.split_frontmatter(updated.decode().replace('\r\n','\n'))
    assert new_meta['generated_visuals']==artifact
    assert new_meta['historical_graph_metadata']==old_meta['generated_visuals']
    assert new_meta['agent']==old_meta['agent']
    row=dict(page='example.md',original_sha256=module.hashlib.sha256(original).hexdigest(),
             updated_sha256=module.hashlib.sha256(updated).hexdigest(),body_unchanged=True,new_inference=False)
    assert module.retain_revalidation_row(row,original,updated)==row
    if eol=='\r\n':
        with pytest.raises(ValueError,match='byte identities'):
            module.retain_revalidation_row(row,original.replace(b'\r\n',b'\n'),updated)
    with pytest.raises(ValueError,match='byte identities'):
        module.retain_revalidation_row(row,original,updated+b'changed')


def test_crlf_revalidation_workflow_retains_actual_file_hashes_on_repeat(tmp_path,monkeypatch):
    path=Path(__file__).parents[1]/'examples/libcamera/validation/issue252/revalidate_visuals.py'
    spec=importlib.util.spec_from_file_location('issue252_visual_repeat',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    run=tmp_path/'run';manuscripts=run/'manuscripts';manuscripts.mkdir(parents=True)
    original=b'---\r\nagent: synthetic-historical-model\r\ngenerated_visuals:\r\n  schema: 1\r\n  records: {}\r\n---\r\n# Unchanged body\r\n\r\nEvidence text.\r\n'
    target=manuscripts/'legacy.md';target.write_bytes(original)
    cfg=SimpleNamespace(sdd_dir=manuscripts,facts_path=run/'facts.json',sections=lambda:[{'id':'legacy'}])
    monkeypatch.setattr(module,'RUN',run)
    monkeypatch.setattr(module,'load',lambda _:cfg)
    monkeypatch.setattr(module.KnowledgeModel,'load',lambda _:object())
    monkeypatch.setattr(module,'for_page',lambda cfg,_:cfg)
    monkeypatch.setattr(module,'section_output',lambda _:'legacy.md')
    monkeypatch.setattr(module.generated_visuals,'plans',lambda *_:True)
    def resolve(_cfg,_model,_section,artifact):
        if not artifact.get('current'):
            raise ValueError('Synthetic historical binding needs metadata revalidation.')
    monkeypatch.setattr(module.generated_visuals,'resolve',resolve)
    monkeypatch.setattr(module.generated_visuals,'generate',lambda *_:dict(schema=1,current=True,records={'synthetic':{'reused':True,'citation_binding_revalidation':{'new_inference':False}}}))
    module.main()
    report=run/'visual-revalidation.json';first=report.read_bytes();row=json.loads(first)[0]
    snapshot=run/row['original_file']
    assert snapshot.read_bytes()==original
    assert row['original_sha256']==module.hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert row['updated_sha256']==module.hashlib.sha256(target.read_bytes()).hexdigest()
    current=target.read_bytes()
    module.main()
    assert report.read_bytes()==first and target.read_bytes()==current
    replacement=original.replace(b'Evidence text.',b'New public evidence text.')
    target.write_bytes(replacement)
    module.main()
    next_report=report.read_bytes();new_row=json.loads(next_report)[0]
    assert new_row['original_file']!=row['original_file']
    assert snapshot.read_bytes()==original
    assert (run/new_row['original_file']).read_bytes()==replacement
    assert new_row['updated_sha256']==module.hashlib.sha256(target.read_bytes()).hexdigest()
    assert any(p.read_bytes()==first for p in (run/'visual-revalidation-history').glob('*.json'))
    module.main()
    assert report.read_bytes()==next_report
