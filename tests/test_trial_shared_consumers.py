"""Common integrity checks leave each trial consumer's reuse decisions intact."""
import hashlib
import json

import pytest

from sdd.call_records import canonical_request_hash
from sdd.config import AgentConfig, load
from sdd.evaluate_reader import evaluate
from sdd.reader_loop import latest_response
from sdd.repair_reader import import_calls, repair


def archived(folder, name, tag, raw, *, transport='ollama', http=True, when='2026-10-26T12:00:00'):
    folder.mkdir(parents=True, exist_ok=True)
    request = {'system': 'policy', 'user': 'same question', 'response_schema': None}
    receipt = dict(tag=tag, completed_at=when, transport=transport, model='test-model',
                   http_call=http, cli_call=transport == 'cli',
                   settings=dict(temperature=.1, think=False, num_ctx=0, max_output_tokens=1500),
                   request_sha256=canonical_request_hash(request),
                   response_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest())
    path = folder / (name + '.receipt.json')
    path.write_text(json.dumps(receipt), encoding='utf-8')
    path.with_name(name + '.request.json').write_text(json.dumps(request), encoding='utf-8')
    path.with_name(name + '.response.txt').write_bytes(raw.encode('utf-8'))
    return path


def test_http_import_keeps_response_bytes_and_does_not_mutate_origin(tmp_path):
    seed = tmp_path / 'seed'
    raw = '첫 줄\r\nsecond line\n'
    receipt_path = archived(seed / 'calls', '001', 'page_topic_0', raw)
    before = {path: path.read_bytes() for path in receipt_path.parent.iterdir()}
    cfg = AgentConfig(kind='ollama', model='test-model')
    destination, bundle = tmp_path / 'imported', tmp_path / 'responses'
    assert import_calls(seed, cfg, destination, bundle) == 1
    imported = destination / '001.response.txt'
    assert imported.read_bytes() == raw.encode('utf-8')
    data = json.loads(next(bundle.glob('*.response.json')).read_text(encoding='utf-8'))
    assert data['response'] == raw
    assert {path: path.read_bytes() for path in receipt_path.parent.iterdir()} == before


def test_http_import_refuses_integrity_valid_cli_record_before_copying(tmp_path):
    seed = tmp_path / 'seed'
    archived(seed / 'calls', '001', 'page_topic_0', 'CLI output', transport='cli', http=False)
    cfg = AgentConfig(kind='cli', model='test-model')
    with pytest.raises(ValueError, match='HTTP origin'):
        import_calls(seed, cfg, tmp_path / 'imported', tmp_path / 'responses')
    assert not (tmp_path / 'imported').exists()
    assert not (tmp_path / 'responses').exists()


@pytest.mark.parametrize('reason', ['done_reason', 'finish_reason'])
def test_http_import_rejects_parseable_truncated_response_before_any_copy(tmp_path, reason):
    seed = tmp_path / 'seed'
    path = archived(seed / 'calls', '001', 'page_topic_0', '{"statements": []}')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    receipt['provider'] = {reason: 'length'}
    path.write_text(json.dumps(receipt), encoding='utf-8')
    original = {item: item.read_bytes() for item in path.parent.iterdir()}
    cfg = AgentConfig(kind='ollama', model='test-model')
    with pytest.raises(ValueError, match='Incomplete HTTP response'):
        import_calls(seed, cfg, tmp_path / 'imported', tmp_path / 'responses')
    assert not (tmp_path / 'imported').exists()
    assert not (tmp_path / 'responses').exists()
    assert {item: item.read_bytes() for item in path.parent.iterdir()} == original


@pytest.mark.parametrize('consumer', ['provenance', 'repair', 'replay'])
@pytest.mark.parametrize('cli_flag', ['missing', False, True])
def test_http_consumers_keep_legacy_receipts_but_reject_cli_origin(tmp_path, consumer, cli_flag):
    from sdd.design_replay import Archive
    from sdd.facts.model import KnowledgeModel
    from sdd.provenance import verify_calls

    seed = tmp_path / 'seed'
    calls = seed / 'calls'
    path = archived(calls, '001', 'page_topic_0', '{}')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if cli_flag == 'missing':
        receipt.pop('cli_call')
    else:
        receipt['cli_call'] = cli_flag
    path.write_text(json.dumps(receipt), encoding='utf-8')
    originals = {item: item.read_bytes() for item in calls.iterdir()}
    cfg = AgentConfig(kind='ollama', model='test-model')
    if consumer == 'replay':
        archive = Archive(calls, cfg)
        assert len(archive.exact) == (0 if cli_flag is True else 1)
    elif consumer == 'repair':
        if cli_flag is True:
            with pytest.raises(ValueError, match='HTTP origin'):
                import_calls(seed, cfg, tmp_path / 'imported', tmp_path / 'responses')
            assert not (tmp_path / 'imported').exists() and not (tmp_path / 'responses').exists()
        else:
            assert import_calls(seed, cfg, tmp_path / 'imported', tmp_path / 'responses') == 1
    elif cli_flag is True:
        with pytest.raises(ValueError, match='receipt mismatch'):
            verify_calls(KnowledgeModel(), tmp_path / 'manuscripts', calls,
                         provider='ollama', model_name='test-model')
    else:
        report = verify_calls(KnowledgeModel(), tmp_path / 'manuscripts', calls,
                              provider='ollama', model_name='test-model')
        assert report['verified_http_calls'] == 1 and report['verified_cli_calls'] == 0
    assert {item: item.read_bytes() for item in calls.iterdir()} == originals


def test_latest_response_keeps_tag_filter_and_exact_raw_response(tmp_path):
    calls = tmp_path / 'prompts/calls'
    raw = 'answer\r\ncontinued\n'
    archived(calls, '001', 'page_topic_0', raw)
    # A non-selected tag's incomplete response is not a producer answer for this unit.
    other = archived(calls, '002', 'page_topic_extra_0', 'unrelated')
    other.with_name('002.response.txt').unlink()
    receipt, response = latest_response(tmp_path, 'page/topic')
    assert response == raw
    assert receipt['response_sha256'] == hashlib.sha256(raw.encode('utf-8')).hexdigest()
    calls.joinpath('001.response.txt').write_text('altered', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum mismatch'):
        latest_response(tmp_path, 'page/topic')


def test_latest_response_assembles_latest_subquestions_with_origin_hashes(tmp_path):
    calls = tmp_path / 'replay-prompts/calls'
    archived(calls, '001', 'page_topic_part_sub1_0', '{"statements": [{"text": "old"}]}',
             when='2026-10-26T11:00:00')
    archived(calls, '002', 'page_topic_part_sub1_1', '{"statements": [{"text": "new"}]}')
    archived(calls, '003', 'page_topic_part_sub2_0', '{"statements": [{"text": "second"}]}')
    receipt, raw = latest_response(tmp_path, 'page/topic/part')
    assert json.loads(raw) == {'statements': [{'text': 'new', 'subpart_id': 1},
                                            {'text': 'second', 'subpart_id': 2}]}
    assert receipt['assembly'] == 'subquestion-responses'
    assert len(receipt['origins']) == 2
    assert receipt['response_sha256'] == hashlib.sha256(raw.encode('utf-8')).hexdigest()


def test_reader_trial_snapshot_preserves_cli_and_operational_input_paths(tmp_cfg, tmp_path,
                                                                        sample_model, monkeypatch):
    cfg = tmp_cfg
    cfg.agent.kind, cfg.agent.runner, cfg.agent.model = 'cli', 'claude', 'chosen-model'
    cfg.agent.allow_direct_api = False
    cfg.agent.args = ['--explicit', 'setting']
    cfg.sections_file.write_text('sections:\n- id: overview\n  title: Overview\n  design_generation: llm\n', encoding='utf-8')
    sample_model.save(cfg.facts_path)
    originals = {path: path.read_bytes() for path in [cfg.sections_file, cfg.facts_path]}
    collected = []

    def collect_snapshot(trial, model):
        assert trial.sections_file != cfg.sections_file
        assert trial.sections_file.read_bytes() == originals[cfg.sections_file]
        collected.append(trial.sections_file)

    monkeypatch.setattr('sdd.evaluate_reader.collect', collect_snapshot)

    def fail_generation(self, selected):
        assert self.cfg.agent.label == 'cli/claude/chosen-model'
        assert self.cfg.prompts_dir == cfg.prompts_dir
        raise ValueError('synthetic automatic failure')

    monkeypatch.setattr('sdd.evaluate_reader.Generator.run', fail_generation)
    out = tmp_path / 'trial'
    report = evaluate(cfg, ['overview'], out, agent_factory=lambda *_: object())
    snapshot = load(out / 'sdd.yaml')
    assert snapshot.agent == cfg.agent
    assert snapshot.source_root == cfg.source_root
    assert snapshot.prompts_dir == cfg.prompts_dir
    assert snapshot.sdd_dir == out / 'manuscripts'
    assert snapshot.sections_file.read_bytes() == originals[cfg.sections_file]
    assert report['human_approval'] == 'pending' and report['publishable'] is False
    assert collected == [out / 'sections.yaml']
    assert all(path.read_bytes() == original for path, original in originals.items())


@pytest.mark.parametrize('fails', [False, True])
def test_repair_counts_live_chat_attempts_without_agent_private_counter(tmp_cfg, tmp_path,
                                                                      sample_model, monkeypatch, fails):
    cfg = tmp_cfg
    cfg.agent.kind, cfg.agent.model = 'ollama', 'test-model'
    cfg.sections_file.write_text('sections:\n- id: overview\n  title: Overview\n  design_generation: llm\n', encoding='utf-8')
    sample_model.save(cfg.facts_path)
    seed = tmp_path / 'seed'
    archived(seed / 'calls', '001', 'overview_topic_0', 'original response')
    (seed / 'evaluation.json').write_text(json.dumps({'source_commit': sample_model.meta['source_commit']}))
    monkeypatch.setattr('sdd.repair_reader.collect', lambda *_: None)

    class ChatOnly:
        def chat(self, system, user, **kwargs):
            if fails:
                raise RuntimeError('synthetic live failure')
            return 'new raw response'

    def generate(self, selected):
        assert self.agent.chat('changed policy', 'new question') == 'new raw response'
        return []

    monkeypatch.setattr('sdd.repair_reader.Generator.run', generate)
    out = tmp_path / 'repair'
    result = repair(cfg, seed, ['overview'], out, agent_factory=lambda *_: ChatOnly())
    assert result['new_http_attempts'] == 1
    assert result['reused_responses'] == 0
    assert result['results'][0]['automatic_checks'] == ('failed' if fails else 'passed')
    assert result['human_approval'] == 'pending' and result['publishable'] is False


def test_pipeline_snapshot_uses_effective_cli_settings_and_same_section_input(tmp_cfg, tmp_path):
    from sdd.evaluate_pipeline import evaluate as evaluate_pipeline

    cfg = tmp_cfg
    cfg.agent.kind, cfg.agent.runner, cfg.agent.model = 'cli', 'hermes', 'explicit-model'
    cfg.agent.args = ['--actual-setting']
    cfg.agent.allow_direct_api = False
    cfg.require_citations, cfg.max_retries, cfg.package_depth = False, 5, 3
    cfg.sections_file.write_text('sections:\n- id: overview\n  title: Overview\n', encoding='utf-8')
    original = cfg.sections_file.read_bytes()
    out = tmp_path / 'pipeline'
    # Missing facts stop before any model invocation while preserving the setup report.
    report = evaluate_pipeline(cfg, out)
    assert report['stages'][-1]['stage'] == 'evidence'
    assert report['stages'][-1]['status'] == 'failed'
    snapshot = load(out / 'sdd.yaml')
    assert snapshot.agent == cfg.agent
    assert snapshot.require_citations is False and snapshot.max_retries == 5
    assert snapshot.package_depth == 3
    assert snapshot.sections_file == out / 'sections.yaml'
    assert snapshot.sections_file.read_bytes() == original == cfg.sections_file.read_bytes()
    assert snapshot.prompts_dir == cfg.prompts_dir
    assert report['sections_sha256'] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize('when', ['initial-read', 'report-hash'])
def test_repair_rejects_linked_seed_report_at_each_read(tmp_cfg, tmp_path, sample_model, monkeypatch, when):
    from pathlib import Path

    cfg = tmp_cfg
    cfg.agent.kind, cfg.agent.model = 'ollama', 'test-model'
    cfg.sections_file.write_text('sections:\n- id: overview\n  title: Overview\n  design_generation: llm\n', encoding='utf-8')
    sample_model.save(cfg.facts_path)
    seed = tmp_path / 'seed'
    archived(seed / 'calls', '001', 'overview_topic_0', 'original response')
    report_path = seed / 'evaluation.json'
    report_bytes = json.dumps({'source_commit': sample_model.meta['source_commit']}).encode('utf-8')
    report_path.write_bytes(report_bytes)
    linked = when == 'initial-read'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: (linked and path == report_path) or original(path))
    monkeypatch.setattr('sdd.repair_reader.collect', lambda *_: None)

    def generate(self, selected):
        nonlocal linked
        linked = True
        return []

    monkeypatch.setattr('sdd.repair_reader.Generator.run', generate)
    out = tmp_path / 'repair'
    with pytest.raises(ValueError, match='symbolic links'):
        repair(cfg, seed, ['overview'], out, agent_factory=lambda *_: object())
    assert report_path.read_bytes() == report_bytes
    assert not (out / 'evaluation.json').exists()
    if when == 'initial-read':
        assert not out.exists()
