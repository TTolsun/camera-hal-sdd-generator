"""Recorded HTTP paragraph selection never rewrites an input or calls a model."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from sdd.document_metadata import split_frontmatter
from sdd.evidence import fingerprint
from sdd.generate import Generator
from sdd.generated_design import verify
from test_generated_design import generated

_spec = importlib.util.spec_from_file_location(
    'consolidate_recorded_answers', Path(__file__).resolve().parents[1] / 'tools/consolidate_recorded_answers.py')
_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tool)
NoCalls, consolidate, statement_sha256 = _tool.NoCalls, _tool.consolidate, _tool.statement_sha256


def _write_page(path, meta, body):
    meta['generated_design']['body_sha256'] = hashlib.sha256(body.strip().encode()).hexdigest()
    path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body, encoding='utf-8', newline='\n')


def _plan_entry(section, path):
    meta, _ = split_frontmatter(path.read_text(encoding='utf-8'))
    statement = meta['generated_design']['answers']['stop'][1]
    return {'original_page_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'before_section': copy.deepcopy(section),
            'remove_statements': [{'topic': 'stop', 'index': 1, 'sha256': statement_sha256(statement)}],
            'remove_parts': []}


@pytest.fixture
def recorded(tmp_cfg, generated, tmp_path, monkeypatch):
    section, model, save, base = generated
    tmp_cfg.raw.setdefault('review', {})['design_grounding'] = True
    class RecordedAgent:
        def chat(self, system, user, **options):
            if options['tag'].endswith('_grounding'):
                return json.dumps({'reviews': [{'index': 0, 'supported': True, 'reason': 'Source matches.'}]})
            return json.dumps({'statements': [base.statement]}, ensure_ascii=False)
    path = Generator(tmp_cfg, model, RecordedAgent()).run()[0]
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    # A frozen older manuscript can predate today's duplicate rejection. Its
    # complete original objects and body are the reviewed maintenance input.
    original = meta['generated_design']['answers']['stop'][0]
    meta['generated_design']['answers']['stop'].append(copy.deepcopy(original))
    _write_page(path, meta, body + '\n\n' + original['text'] + '\n')
    plan = {'schema': 1, 'source_commit': 'a' * 40, 'sections': {'device': _plan_entry(section, path)}}
    monkeypatch.setattr('sdd.llm.Agent.chat', lambda *a, **k: pytest.fail('No transport may execute'))
    return tmp_cfg, model, section, path, plan, tmp_path / 'result'


def test_valid_recomposition_keeps_objects_http_identity_and_zero_calls(recorded, monkeypatch):
    cfg, model, section, path, plan, out = recorded
    original = path.read_bytes()
    original_meta, _ = split_frontmatter(original.decode())
    calls = []
    monkeypatch.setattr(NoCalls, 'chat', lambda *a, **k: calls.append(1) or pytest.fail('No calls allowed'))
    # The current execution setting must never relabel recorded HTTP authorship.
    cfg.agent.kind, cfg.agent.model = 'cli', 'different-model'
    report = consolidate(cfg, model, plan, out)
    output = out / 'manuscripts/device.md'
    meta, _ = split_frontmatter(output.read_text(encoding='utf-8'))
    assert path.read_bytes() == original and calls == []
    assert meta['agent'].startswith('ollama/') and 'cli/' not in meta['agent']
    assert meta['generated_design']['topic_agents'] == original_meta['generated_design']['topic_agents']
    assert meta['generated_design']['answers']['stop'] == original_meta['generated_design']['answers']['stop'][:1]
    assert meta['generated_design']['topic_inputs'] == {}
    assert meta['generated_design']['maintenance_mode'] == 'recorded-http-answer-selection'
    assert meta['generated_design']['maintenance_lineage'][0]['original_page_sha256'] == hashlib.sha256(original).hexdigest()
    assert report['zero_model_calls'] is True and report['human_review'] == 'pending'
    assert report['publishable'] is False and report['mode'] == 'recorded-http-answer-selection'
    assert report['sections']['device']['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads((out / 'recomposition.json').read_text(encoding='utf-8')) == report
    assert verify(model, section, output.read_text(encoding='utf-8'))['human_review'] == 'pending'
    assert sorted(p.name for p in (out / 'manuscripts').glob('*.md')) == ['device.md']


@pytest.mark.parametrize('change', ['page_sha', 'body_sha', 'before_fingerprint', 'unknown_statement',
                                  'statement_sha', 'paragraph_edit', 'question_change', 'commit', 'page_commit',
                                  'cli_origin', 'grounding_policy'])
def test_forged_or_edited_inputs_fail_without_output_or_input_mutation(recorded, change):
    cfg, model, section, path, plan, out = recorded
    entry = plan['sections']['device']
    if change == 'page_sha': entry['original_page_sha256'] = '0' * 64
    elif change == 'before_fingerprint': entry['before_section']['design_topics'][0]['question'] = 'Different question'
    elif change == 'unknown_statement': entry['remove_statements'][0]['index'] = 90
    elif change == 'statement_sha': entry['remove_statements'][0]['sha256'] = '0' * 64
    elif change == 'paragraph_edit': entry['remove_statements'][0]['text'] = 'Edited paragraph'
    elif change == 'question_change':
        section['design_topics'][0]['question'] = 'Different question'
        cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    elif change == 'commit': plan['source_commit'] = 'b' * 40
    else:
        meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
        if change == 'body_sha':
            body += '\nEdited body without updating its hash.'
            path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body, encoding='utf-8')
        else:
            if change == 'page_commit': meta['source_commit'] = 'b' * 40
            elif change == 'cli_origin': meta['generated_design']['topic_agents']['stop'] = 'cli/hermes/model'
            else: meta['generated_design']['grounding_policy'] = '0' * 64
            _write_page(path, meta, body)
        entry['original_page_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    original, config = path.read_bytes(), cfg.sections_file.read_bytes()
    with pytest.raises(ValueError): consolidate(cfg, model, plan, out)
    assert path.read_bytes() == original and cfg.sections_file.read_bytes() == config
    assert not out.exists()
    assert not list(out.parent.glob('.recorded-answers-*'))


def _parts(recorded, remove_part):
    cfg, model, section, path, plan, _ = recorded
    parts = [{'id': pid, 'question': '종료 처리는 무엇입니까?', 'sources': ['stop'], 'max_statements': 1}
             for pid in ('first', 'duplicate')]
    before = copy.deepcopy(section)
    before['design_topics'][0]['parts'] = parts
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    for statement, part in zip(meta['generated_design']['answers']['stop'], parts):
        statement['part_id'] = part['id']
    meta['evidence_fingerprint'] = meta['generated_design']['input_fingerprint'] = fingerprint(model, before)
    _write_page(path, meta, body)
    section['design_topics'][0]['parts'] = parts[:1] if remove_part else parts
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    plan['sections']['device'] = _plan_entry(before, path)
    if remove_part:
        plan['sections']['device']['remove_parts'] = [{'topic': 'stop', 'part_id': 'duplicate'}]


def test_removed_paragraph_cannot_break_remaining_part_coverage(recorded):
    _parts(recorded, False)
    cfg, model, _, path, plan, out = recorded
    original = path.read_bytes()
    with pytest.raises(ValueError, match='질문|답변'): consolidate(cfg, model, plan, out)
    assert path.read_bytes() == original and not out.exists()


def test_explicit_duplicate_part_removal_preserves_original_part_identity(recorded):
    _parts(recorded, True)
    cfg, model, _, path, plan, out = recorded
    consolidate(cfg, model, plan, out)
    meta, _ = split_frontmatter((out / 'manuscripts/device.md').read_text(encoding='utf-8'))
    assert meta['generated_design']['answers']['stop'][0]['part_id'] == 'first'
    assert len(meta['generated_design']['answers']['stop']) == 1
    assert meta['generated_design']['maintenance_lineage'][0]['removed_parts'] == [{'topic': 'stop', 'part_id': 'duplicate'}]


def test_partial_render_failure_preserves_all_inputs_and_no_destination(recorded, monkeypatch):
    cfg, model, section, path, plan, out = recorded
    other = {**copy.deepcopy(section), 'id': 'other', 'output': 'other.md'}
    for key, value in list(model.evidence.items()):
        model.evidence[key.replace('device/', 'other/', 1)] = copy.deepcopy(value)
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['section'] = 'other'
    meta['evidence_fingerprint'] = meta['generated_design']['input_fingerprint'] = fingerprint(model, other)
    second = cfg.sdd_dir / 'other.md'
    _write_page(second, meta, body)
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section, other]}, allow_unicode=True), encoding='utf-8')
    plan['sections']['other'] = _plan_entry(other, second)
    originals = {p: p.read_bytes() for p in (path, second)}
    render, visited = Generator._prose, []
    def fail_second(self, selected):
        visited.append(selected['id'])
        if selected['id'] == 'other': raise OSError('Second staged output failed')
        return render(self, selected)
    monkeypatch.setattr(Generator, '_prose', fail_second)
    with pytest.raises(OSError): consolidate(cfg, model, plan, out)
    assert visited == ['device', 'other']
    assert not out.exists() and all(p.read_bytes() == original for p, original in originals.items())
    assert not list(out.parent.glob('.recorded-answers-*'))


@pytest.mark.parametrize('where', ['trial', 'manuscripts', 'source', 'facts'])
def test_output_never_overlaps_original_inputs(recorded, where):
    cfg, model, _, _, plan, _ = recorded
    root = {'trial': cfg.root, 'manuscripts': cfg.sdd_dir, 'source': cfg.source_root, 'facts': cfg.facts_dir}[where]
    with pytest.raises(ValueError, match='isolated|new output'):
        consolidate(cfg, model, plan, root / 'result')


def test_existing_destination_is_preserved(recorded):
    cfg, model, _, path, plan, out = recorded
    out.mkdir()
    sentinel = out / 'keep.txt'
    sentinel.write_bytes(b'Existing output')
    original = path.read_bytes()
    with pytest.raises(ValueError): consolidate(cfg, model, plan, out)
    assert sentinel.read_bytes() == b'Existing output' and path.read_bytes() == original


def test_preserves_original_http_time_metadata_and_artifact_fields(recorded):
    from datetime import datetime
    cfg, model, section, path, plan, out = recorded
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['generated_at'] = datetime.fromisoformat('2024-01-02T03:04:05+00:00')
    meta['producer_version'] = 'historical HTTP execution'
    meta['generated_design']['original_transport_receipt'] = {'run': 'historical-http'}
    _write_page(path, meta, body)
    plan['sections']['device'] = _plan_entry(section, path)
    original = path.read_bytes()
    report = consolidate(cfg, model, plan, out)
    result, _ = split_frontmatter((out / 'manuscripts/device.md').read_text(encoding='utf-8'))
    for key in ('generated_at', 'agent', 'generation_method', 'source_commit', 'producer_version'):
        assert result[key] == meta[key]
    allowed = {'answers', 'input_fingerprint', 'topic_inputs', 'body_sha256', 'maintenance_mode', 'maintenance_lineage'}
    for key, value in meta['generated_design'].items():
        if key not in allowed:
            assert result['generated_design'][key] == value
    maintained = result['generated_design']['maintenance_lineage'][-1]['maintained_at']
    assert datetime.fromisoformat(maintained) > meta['generated_at']
    assert report['sections']['device']['maintained_at'] == maintained
    assert path.read_bytes() == original


def test_missing_original_authorship_timestamp_is_not_replaced_by_maintenance_clock(recorded):
    cfg, model, section, path, plan, out = recorded
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta.pop('generated_at')
    _write_page(path, meta, body)
    plan['sections']['device'] = _plan_entry(section, path)
    consolidate(cfg, model, plan, out)
    result, _ = split_frontmatter((out / 'manuscripts/device.md').read_text(encoding='utf-8'))
    assert 'generated_at' not in result
    assert result['generated_design']['maintenance_lineage'][-1]['maintained_at']


def test_original_paragraph_edit_cannot_change_the_reviewed_page_identity(recorded):
    cfg, model, _, path, plan, out = recorded
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['generated_design']['answers']['stop'][0]['text'] += ' 추가한 새 문장입니다.'
    _write_page(path, meta, body)
    with pytest.raises(ValueError, match='page SHA256'): consolidate(cfg, model, plan, out)
    assert not out.exists()


def test_required_terms_can_only_be_strengthened(recorded):
    cfg, model, section, path, plan, out = recorded
    section['design_topics'][0]['answer_contract'] = {'basis': 'implementation', 'required_terms': [['stop']]}
    # Adding an entire new contract is not the allowed required_terms-only edit.
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='Contract changes'): consolidate(cfg, model, plan, out)


@pytest.mark.parametrize('change,valid', [('narrow', True), ('add_group', True), ('weaken', False),
                                         ('basis', False), ('remove_rejection', False)])
def test_existing_required_terms_strengthening_keeps_all_other_checks(recorded, change, valid):
    cfg, model, section, path, plan, out = recorded
    before = copy.deepcopy(section)
    before['design_topics'][0]['answer_contract'] = {
        'basis': 'implementation', 'required_terms': [['stop', 'cancelPending']],
        'reject_patterns': [{'pattern': 'FORBIDDEN', 'message': 'Forbidden claim'}]}
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['evidence_fingerprint'] = meta['generated_design']['input_fingerprint'] = fingerprint(model, before)
    _write_page(path, meta, body)
    plan['sections']['device'] = _plan_entry(before, path)
    section['design_topics'][0]['answer_contract'] = copy.deepcopy(before['design_topics'][0]['answer_contract'])
    rule = section['design_topics'][0]['answer_contract']
    if change == 'narrow': rule['required_terms'] = [['stop']]
    elif change == 'add_group': rule['required_terms'].append(['취소'])
    elif change == 'weaken': rule['required_terms'][0].append('anything')
    elif change == 'basis': rule['basis'] = 'contract'
    else: rule.pop('reject_patterns')
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    original = path.read_bytes()
    if valid:
        consolidate(cfg, model, plan, out)
        assert (out / 'manuscripts/device.md').exists()
    else:
        with pytest.raises(ValueError): consolidate(cfg, model, plan, out)
        assert not out.exists()
    assert path.read_bytes() == original


def test_crlf_input_binds_original_bytes_and_core_normalized_body_hash(recorded):
    cfg, model, _, path, plan, out = recorded
    original = path.read_bytes().replace(b'\n', b'\r\n')
    path.write_bytes(original)
    plan['sections']['device']['original_page_sha256'] = hashlib.sha256(original).hexdigest()
    consolidate(cfg, model, plan, out)
    assert path.read_bytes() == original


def test_current_grounding_requirement_cannot_be_satisfied_by_an_unreviewed_record(recorded):
    cfg, model, section, path, plan, out = recorded
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['generated_design'].pop('grounding_review')
    _write_page(path, meta, body)
    plan['sections']['device'] = _plan_entry(section, path)
    with pytest.raises(ValueError, match='existing passed review'):
        consolidate(cfg, model, plan, out)
    assert not out.exists()


def test_unchanged_topic_request_identity_and_whole_statement_are_preserved(recorded):
    cfg, model, section, path, plan, out = recorded
    source = {'id': 'init', 'file': 'device.cpp', 'start': 'int initialize()', 'end': '}'}
    code = 'int initialize() { return 0; }'
    model.evidence['device/initialize/init'] = {
        'selector': source, 'commit': 'a' * 40, 'file': 'device.cpp', 'line': 20, 'end_line': 20,
        'text': code, 'sha256': hashlib.sha256(code.encode()).hexdigest(), 'status': 'available'}
    section['design_requirements'].append({'id': 'initialize', 'question': '초기화 함수는 무엇을 반환합니까?'})
    section['design_topics'].append({'id': 'initialize', 'title': '초기화 결과',
        'question': '초기화 함수는 무엇을 반환합니까?', 'covers': ['initialize'], 'sources': [source]})
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    statement = {'text': '`initialize()` 함수는 정수 0을 반환합니다.', 'quote': code,
                 'evidence': ['init'], 'covers': ['initialize'], 'kind': 'behavior'}
    artifact = meta['generated_design']
    artifact['answers']['initialize'] = [statement]
    artifact['topic_agents']['initialize'] = artifact['topic_agents']['stop']
    artifact['topic_inputs']['initialize'] = 'b' * 64
    meta['evidence_fingerprint'] = artifact['input_fingerprint'] = fingerprint(model, section)
    _write_page(path, meta, body + '\n\n' + statement['text'] + '\n')
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    plan['sections']['device'] = _plan_entry(section, path)
    consolidate(cfg, model, plan, out)
    result, _ = split_frontmatter((out / 'manuscripts/device.md').read_text(encoding='utf-8'))
    assert result['generated_design']['topic_inputs'] == {'initialize': 'b' * 64}
    assert result['generated_design']['answers']['initialize'] == [statement]


def test_current_node_limit_is_not_bypassed(recorded):
    from sdd.facts.model import ClassInfo, Location
    cfg, model, section, path, plan, out = recorded
    for name in ('First', 'Second'):
        model.classes[name] = ClassInfo(name=name, loc=Location('device.cpp', 10))
    section['facts'] = {'classes': ['*']}
    section['diagram'] = {'enabled': True, 'max_nodes': 1}
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['evidence_fingerprint'] = meta['generated_design']['input_fingerprint'] = fingerprint(model, section)
    _write_page(path, meta, body)
    cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    plan['sections']['device'] = _plan_entry(section, path)
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match='nodes'): consolidate(cfg, model, plan, out)
    assert path.read_bytes() == original and not out.exists()


def test_no_calls_port_always_raises():
    with pytest.raises(RuntimeError, match='cannot call'): NoCalls().chat('system', 'question')
