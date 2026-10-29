"""Current reader questions and verified prose bind omission judgments."""
import copy
import json

import pytest
import yaml

from test_generated_design import generated
from test_idle_review import idle_case
from sdd import idle_review
from sdd.generate import Generator


def scoped(section, requirement):
    section['reader_profile'] = 'team'
    section['design_requirements'][0]['aspects'] = ['role', 'inputs', 'outputs', 'boundaries']
    section['reader_scope'] = {'revision': 1, 'change_reason': 'Fixed test task before judgments.',
        'tasks': [{'id': 'collaborate', 'goal': 'Find the responsibility.',
                   'completion': 'Find its answer and conditions.', 'requirements': [requirement]}],
        'optional': [], 'excluded': [], 'removed_requirements': []}


@pytest.mark.parametrize('field', ['design_requirements', 'design_topics'])
def test_changed_question_rechecks_seen_window_with_same_task_revision(idle_case, monkeypatch, field):
    cfg, target = idle_case
    sections = yaml.safe_load(cfg.sections_file.read_text(encoding='utf-8'))
    section = sections['sections'][0]
    scoped(section, 'existing')
    cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    calls = []
    result = {'kind': 'no_gap', 'reason': 'Covered in this fictional window only.',
              'scope_decision': {'disposition': 'already-covered', 'task': 'collaborate',
                  'unmet_need': 'The supplied window repeats the answer.', 'existing_topics': ['existing'],
                  'evidence': ['source-window'], 'detail': ''}}
    monkeypatch.setattr(idle_review, '_ask', lambda *a: (calls.append(a[1]) or copy.deepcopy(result)))
    assert idle_review.run(cfg, target, 'fixed-job')['status'] == 'checked'
    assert idle_review.run(cfg, target, 'fixed-job')['status'] == 'checked'
    assert len(calls) == 1
    section[field][0]['question'] += ' 정확한 책임 범위를 구분하세요.'
    cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    assert idle_review.run(cfg, target, 'fixed-job')['status'] == 'checked'
    assert len(calls) == 2
    assert '정확한 책임 범위' in calls[1]
    assert section['reader_scope']['revision'] == 1


def test_scoped_prompt_reads_verified_llm_answers_and_rejects_modified_manuscript(generated, tmp_cfg):
    section, model, save, agent = generated
    scoped(section, 'shutdown')
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    excerpt = {'file': 'device.cpp', 'offset': 0, 'total_chars': 32, 'text': 'void stop() { cancelPending(); }'}
    prompt = idle_review._prompt(tmp_cfg, tmp_cfg.sections()[0], excerpt)
    selected = json.loads(prompt[prompt.index('{"catalogue":'):])
    row = selected['selected']['topics'][0]['statements'][0]
    assert row['text'] == agent.statement['text']
    assert row['evidence'] == ['stop'] and row['covers'] == ['shutdown']
    assert selected['selected']['existing_manuscript']['source_commit'] == model.meta['source_commit']
    assert '"id":"existing-required-id"' in prompt and '"covers":["existing-required-id"]' in prompt
    identity = idle_review._review_identity(tmp_cfg, 'fixed-base')
    window_input = idle_review._reader_inputs(tmp_cfg, section)
    original = path.read_bytes()
    path.write_bytes(original + '\n설명을 바꿨습니다.\n'.encode('utf-8'))
    assert idle_review._review_identity(tmp_cfg, 'fixed-base') != identity
    assert idle_review._reader_inputs(tmp_cfg, section) != window_input
    with pytest.raises(ValueError, match='원고 본문'):
        idle_review._prompt(tmp_cfg, tmp_cfg.sections()[0], excerpt)
    path.write_bytes(original)
    assert idle_review._review_identity(tmp_cfg, 'fixed-base') == identity


def test_changed_facts_or_style_cannot_reuse_scoped_completion(generated, tmp_cfg):
    section, model, save, agent = generated
    scoped(section, 'shutdown')
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    # This fake generator has no CLI receipts. Declare the original style
    # identity explicitly to exercise the same publication check as CLI prose.
    from sdd.cli_checkpoint import style_policy
    from sdd.document_metadata import split_frontmatter
    meta, body = split_frontmatter(path.read_text(encoding='utf-8'))
    meta['generated_design']['style_policy'] = style_policy(tmp_cfg)
    path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n' + body, encoding='utf-8')
    identity = idle_review._review_identity(tmp_cfg, 'fixed-base')
    facts = tmp_cfg.facts_path.read_bytes()
    model.meta['source_commit'] = 'b'*40
    model.save(tmp_cfg.facts_path)
    assert idle_review._review_identity(tmp_cfg, 'fixed-base') != identity
    with pytest.raises(ValueError, match='커밋이 다릅니다'):
        idle_review._prompt(tmp_cfg, tmp_cfg.sections()[0], {'text': 'void stop() {}'})
    tmp_cfg.facts_path.write_bytes(facts)
    style = tmp_cfg.style_dir/'README.md'
    original = style.read_bytes()
    style.write_bytes(original + b'\nChanged writing rule.\n')
    assert idle_review._review_identity(tmp_cfg, 'fixed-base') != identity
    with pytest.raises(ValueError, match='집필 규칙'):
        idle_review._prompt(tmp_cfg, tmp_cfg.sections()[0], {'text': 'void stop() {}'})
    style.write_bytes(original)
    assert idle_review._review_identity(tmp_cfg, 'fixed-base') == identity


def test_scoped_prompt_rejects_manuscript_from_another_commit(generated, tmp_cfg):
    section, model, save, agent = generated
    scoped(section, 'shutdown')
    save()
    path = Generator(tmp_cfg, model, agent).run()[0]
    text = path.read_text(encoding='utf-8').replace('source_commit: ' + 'a'*40, 'source_commit: ' + 'b'*40)
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match='커밋이 다릅니다'):
        idle_review._prompt(tmp_cfg, tmp_cfg.sections()[0], {'file': 'device.cpp', 'text': 'void stop() {}'})
