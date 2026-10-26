"""Select complete recorded HTTP paragraphs; never generate or rewrite prose.

Plan schema 1: source_commit and sections keyed by section ID. Each entry has
original_page_sha256, before_section, remove_statements [{topic,index,sha256}],
and remove_parts [{topic,part_id}]. Statement hashes cover the entire JSON object
using ensure_ascii=False and sort_keys=True, including its original identities.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from sdd import generated_design, generated_visuals
from sdd.config import load, section_output
from sdd.document_metadata import split_frontmatter
from sdd.evidence import fingerprint
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator
from sdd.trial_workspace import clone_config, contained_path, reject_symlinks, validate_output


def statement_sha256(statement):
    return hashlib.sha256(json.dumps(statement, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class NoCalls:
    def chat(self, *args, **kwargs):
        raise RuntimeError('Recorded-answer maintenance cannot call any model, API or CLI')


def _exact_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f'Unexpected {label} fields')


def _stronger_contract(before, current, path=()):
    """Permit added AND groups or narrower OR alternatives, never weaker rules."""
    if path[-2:] == ('answer_contract', 'required_terms'):
        if not isinstance(before, list) or not isinstance(current, list):
            raise ValueError('required_terms must remain an alternatives list')
        if any(not isinstance(group, list) or not group or any(not isinstance(t, str) for t in group)
               for group in [*before, *current]):
            raise ValueError('Invalid required_terms alternatives')
        if any(not any(set(new) <= set(old) for new in current) for old in before):
            raise ValueError('required_terms cannot be weakened')
        return
    if isinstance(before, dict) and isinstance(current, dict):
        keys = set(before) | set(current)
        for key in keys:
            if key == 'required_terms' and path[-1:] == ('answer_contract',):
                _stronger_contract(before.get(key, []), current.get(key, []), (*path, key))
            elif key not in before or key not in current:
                raise ValueError('Contract changes exceed declared part removal and required_terms strengthening')
            else:
                _stronger_contract(before[key], current[key], (*path, key))
    elif isinstance(before, list) and isinstance(current, list) and len(before) == len(current):
        for old, new in zip(before, current):
            _stronger_contract(old, new, path)
    elif type(before) is not type(current) or before != current:
        raise ValueError('Contract changes exceed declared part removal and required_terms strengthening')


def _select(section, entry, original):
    before = copy.deepcopy(entry['before_section'])
    expected = copy.deepcopy(before)
    topics = {topic['id']: topic for topic in expected['design_topics']}
    removed_parts = set()
    changed = set()
    for item in entry['remove_parts']:
        _exact_fields(item, ('topic', 'part_id'), 'part removal')
        tid, pid = item['topic'], item['part_id']
        if tid not in topics or (tid, pid) in removed_parts:
            raise ValueError('Unknown or repeated part removal')
        parts = topics[tid].get('parts', [])
        if not any(part['id'] == pid for part in parts):
            raise ValueError('Part removal does not identify an original part')
        topics[tid]['parts'] = [part for part in parts if part['id'] != pid]
        removed_parts.add((tid, pid))
        changed.add(tid)
    _stronger_contract(expected, section)
    for old, new in zip(before['design_topics'], section['design_topics']):
        if old != new:
            changed.add(old['id'])
    answers = original['answers']
    removals = set()
    for item in entry['remove_statements']:
        _exact_fields(item, ('topic', 'index', 'sha256'), 'statement removal')
        tid, index = item['topic'], item['index']
        if (tid not in answers or type(index) is not int or not 0 <= index < len(answers[tid])
                or (tid, index) in removals or statement_sha256(answers[tid][index]) != item['sha256']):
            raise ValueError('Statement removal does not match an original whole statement and hash')
        removals.add((tid, index))
        changed.add(tid)
    # A removed part must have all its original statements explicitly selected
    # for deletion. Never retag a surviving paragraph as another part.
    for tid, statements in answers.items():
        for index, statement in enumerate(statements):
            if (tid, statement.get('part_id')) in removed_parts and (tid, index) not in removals:
                raise ValueError('Removed part still has an original statement; list every deletion explicitly')
    if not removals and not removed_parts:
        raise ValueError('The plan must select at least one complete statement or part for removal')
    selected = {tid: [copy.deepcopy(st) for i, st in enumerate(statements) if (tid, i) not in removals]
                for tid, statements in answers.items()}
    return selected, changed


def _prepare(cfg, model, section, entry, source_commit, *, paragraph_layout):
    _exact_fields(entry, ('original_page_sha256', 'before_section', 'remove_statements', 'remove_parts'), 'section plan')
    if not isinstance(entry['remove_statements'], list) or not isinstance(entry['remove_parts'], list):
        raise ValueError('Removal selections must be lists')
    before = entry['before_section']
    if (not isinstance(before, dict) or before.get('id') != section['id']
            or not generated_design.enabled(before) or not generated_design.enabled(section)):
        raise ValueError('Only explicitly identified generated-design prose sections are supported')
    if section.get('kind', 'prose') != 'prose':
        raise ValueError('Recorded-answer consolidation supports prose pages only')
    source = contained_path(cfg.sdd_dir, section_output(before))
    raw = source.read_bytes()
    page_sha = hashlib.sha256(raw).hexdigest()
    if page_sha != entry['original_page_sha256']:
        raise ValueError('Original page SHA256 mismatch')
    # Match Path.read_text's universal-newline behavior used by core validators;
    # the independent page SHA above still binds every original byte.
    text = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    meta, body = split_frontmatter(text)
    artifact = meta.get('generated_design')
    if (meta.get('source_commit') != source_commit or meta.get('section') != section['id']
            or not isinstance(artifact, dict) or artifact.get('schema') != 1
            or artifact.get('body_sha256') != generated_design.digest(body.strip())
            or artifact.get('input_fingerprint') != fingerprint(model, before)
            or (meta.get('evidence_fingerprint') is not None
                and meta['evidence_fingerprint'] != fingerprint(model, before))):
        raise ValueError('Original source commit, body hash or before_section fingerprint mismatch')
    answers, agents = artifact.get('answers'), artifact.get('topic_agents')
    if (not isinstance(answers, dict) or not answers or not isinstance(agents, dict) or set(answers) != set(agents)
            or any(not isinstance(label, str) or label.partition('/')[0] not in ('ollama', 'openai-compatible')
                   or not label.partition('/')[2] for label in agents.values())):
        raise ValueError('Every original answer must have an explicit HTTP producer')
    grounding_required = section.get('design_grounding', (cfg.raw.get('review') or {}).get('design_grounding', False))
    if grounding_required and artifact.get('grounding_review') != 'passed':
        raise ValueError('Current grounding requirements need an existing passed review; maintenance cannot create one')
    generated_design.preflight(model, before)
    selected, changed = _select(section, entry, artifact)
    pinned, resolved, validation = generated_design.validate_answers(model, section, selected)
    lineage = {'mode': 'recorded-http-answer-selection', 'source_commit': source_commit,
               'paragraph_layout': paragraph_layout,
               'maintained_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'original_page_sha256': page_sha, 'original_body_sha256': artifact['body_sha256'],
               'before_input_fingerprint': artifact['input_fingerprint'],
               'removed_statements': copy.deepcopy(entry['remove_statements']),
               'removed_parts': copy.deepcopy(entry['remove_parts']),
               'selected_statements': {tid: [statement_sha256(st) for st in rows] for tid, rows in selected.items()},
               'original_producers': copy.deepcopy(agents), 'zero_model_calls': True, 'human_review': 'pending'}
    updated = copy.deepcopy(artifact)
    updated.update(answers=selected, input_fingerprint=fingerprint(model, section),
                   maintenance_mode='recorded-http-answer-selection')
    updated['topic_inputs'] = {tid: value for tid, value in artifact.get('topic_inputs', {}).items() if tid not in changed}
    history = updated.get('maintenance_lineage', [])
    if not isinstance(history, list):
        raise ValueError('Invalid original maintenance lineage')
    updated['maintenance_lineage'] = [*history, lineage]
    visual = generated_visuals.from_manuscript(cfg, model, before, text)
    return (pinned, resolved, validation, updated), visual, lineage, meta


def _preserve_producer_metadata(path, original):
    """Rendering is maintenance, so its clock must not replace authorship time."""
    metadata, body = split_frontmatter(path.read_text(encoding='utf-8'))
    derived = {'generated_design', 'generated_visuals', 'evidence_fingerprint',
               'status', 'semantic_review', 'facts_omitted'}
    for key, value in original.items():
        if key not in derived:
            metadata[key] = copy.deepcopy(value)
    for key in ('generated_at', 'agent', 'generation_method'):
        if key not in original:
            metadata.pop(key, None)
    # Only frontmatter is restored. The already-validated body, bindings and
    # current automatic-check result remain the common renderer's output.
    text = '---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + '---\n' + body
    path.write_text(text, encoding='utf-8', newline='\n')


def consolidate(cfg, model, plan, out, *, grouped=True):
    """Validate every selection, render in isolation, then promote the whole batch."""
    if type(grouped) is not bool:
        raise ValueError('grouped must be a boolean')
    paragraph_layout = 'grouped' if grouped else 'legacy'
    _exact_fields(plan, ('schema', 'source_commit', 'sections'), 'plan')
    commit = plan['source_commit']
    if (type(plan['schema']) is not int or plan['schema'] != 1 or not isinstance(commit, str)
            or not re.fullmatch(r'[0-9a-f]{40}', commit) or model.meta.get('source_commit') != commit):
        raise ValueError('Plan and model must identify the same full source commit')
    if not isinstance(plan['sections'], dict) or not plan['sections']:
        raise ValueError('Select at least one section')
    reject_symlinks(cfg.sdd_dir, recursive=True)
    out = validate_output(cfg, Path(out), previous=[cfg.root])
    configured = cfg.sections()
    sections = {section['id']: section for section in configured}
    if len(sections) != len(configured) or not set(plan['sections']) <= set(sections):
        raise ValueError('Unknown or duplicate section IDs')
    prepared, reports = {}, {}
    outputs = set()
    for sid, entry in plan['sections'].items():
        relative = section_output(sections[sid])
        if '\\' in relative or ':' in relative:
            raise ValueError('Page outputs must be relative POSIX paths without streams')
        if relative in outputs:
            raise ValueError('Selected pages have conflicting output paths')
        contained_path(out / 'manuscripts', relative)
        outputs.add(relative)
        prepared[sid], visual, reports[sid], original_meta = _prepare(
            cfg, model, sections[sid], entry, commit, paragraph_layout=paragraph_layout)
        prepared[sid] = (prepared[sid], visual, original_meta)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.recorded-answers-', dir=out.parent) as temporary:
        stage = Path(temporary)
        trial = clone_config(cfg, stage)
        generator = Generator(trial, model, NoCalls())
        for sid, (design, visual, original_meta) in prepared.items():
            generator.generated_designs[sid] = design
            if visual:
                generator.generated_visuals[sid] = visual
            path = generator._prose(sections[sid], grouped=grouped)
            _preserve_producer_metadata(path, original_meta)
            text = path.read_text(encoding='utf-8')
            generated_design.verify(model, sections[sid], text)
            metadata, _ = split_frontmatter(text)
            if metadata['generated_design']['answers'] != design[3]['answers']:
                raise ValueError('Common renderer changed selected statement objects')
            reports[sid] = {**reports[sid], 'output': path.relative_to(stage).as_posix(),
                            'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        report = {'schema': 1, 'mode': 'recorded-http-answer-selection', 'source_commit': commit,
                  'paragraph_layout': paragraph_layout,
                  'sections': reports, 'zero_model_calls': True, 'human_review': 'pending', 'publishable': False}
        (stage / 'recomposition.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        if out.exists():
            raise ValueError('Output appeared during staging; refusing to overwrite it')
        stage.rename(out)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--facts', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--legacy-paragraphs', action='store_true',
                        help='Preserve the legacy one-statement-per-paragraph layout and citation order')
    args = parser.parse_args()
    cfg = load(args.config)
    report = consolidate(cfg, KnowledgeModel.load(args.facts or cfg.facts_path),
                         json.loads(args.plan.read_text(encoding='utf-8')), args.out,
                         grouped=not args.legacy_paragraphs)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
