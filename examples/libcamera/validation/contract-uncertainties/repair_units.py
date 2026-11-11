"""Draft selected native CLI units and reassemble without promoting old origins.

This example recipe keeps unaffected statements and their historical topic
identities. It does not manufacture a new full-page generation or human approval.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from sdd.config import load
from sdd.contract_schema import configuration_errors
from sdd.design_execution import _request_unit
from sdd.design_checkpoint import store_for
from sdd.design_request import _design_units, prepare_requests
from sdd.document_metadata import split_frontmatter
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator
from sdd.generated_design import _assemble_generation
from sdd.generation_run import Execution
from sdd.grounding import policy_hash
from sdd.llm import Agent


def repair(config: Path, targets: Path, output: Path) -> None:
    cfg = load(config)
    assert cfg.agent.kind == 'cli' and cfg.agent.runner == 'codex'
    assert cfg.agent.model == 'gpt-6.1-terra'
    assert 'model_reasoning_effort="high"' in cfg.agent.args
    for section in cfg.sections():
        if errors := configuration_errors(section):
            raise ValueError(' / '.join(errors))
    output.mkdir(parents=True, exist_ok=False)
    original_sdd = cfg.sdd_dir
    staged_cfg = copy.deepcopy(cfg)
    staged_cfg.sdd_dir = output / 'staged-manuscripts'
    staged_cfg.diagrams_dir = staged_cfg.sdd_dir / 'diagrams'
    shutil.copytree(original_sdd, staged_cfg.sdd_dir)
    model = KnowledgeModel.load(cfg.facts_path)
    selected = json.loads(targets.read_bytes())
    assert len({(r['section'], r['topic'], r['part']) for r in selected}) == len(selected)
    # Native checkpoints bind receipts below this exact configured calls root.
    dump = cfg.build_dir / 'prompts'
    agent = Agent(cfg.agent, dump)
    agent._counter = max((int(p.name.split('_', 1)[0]) for p in dump.glob('*_*.md')
                          if p.name.split('_', 1)[0].isdigit()), default=0)
    execution = Execution(cfg, agent, model=model)
    results, page_paths, originals = [], {}, {}
    with execution.track('selected-question-public-source-repair'):
        for sid in dict.fromkeys(row['section'] for row in selected):
            section = next(s for s in cfg.sections() if s['id'] == sid)
            if errors := configuration_errors(section):
                raise ValueError(' / '.join(errors))
            path = cfg.sdd_dir / section.get('output', sid + '.md')
            page_paths[sid] = path.relative_to(original_sdd)
            before = path.read_bytes()
            originals[page_paths[sid]] = before
            text = path.read_text(encoding='utf-8')
            meta, _ = split_frontmatter(text)
            old = meta['generated_design']
            if old.get('grounding_review') == 'passed':
                assert old['grounding_policy'] == policy_hash()
            (output / (sid + '-before.md')).write_bytes(before)
            wanted = {(r['topic'], r['part']) for r in selected if r['section'] == sid}
            for tid, pid in wanted:
                assert sum(row.get('part_id') == pid for row in old['answers'][tid]) == 1
            units = [u for u in _design_units(section, {}) if (u['id'], u.get('_part_id')) in wanted]
            assert len(units) == len(wanted), 'Target must select complete existing question units'
            answers = copy.deepcopy(old['answers'])
            for tid in answers:
                answers[tid] = [row for row in answers[tid] if (tid, row.get('part_id')) not in wanted]
            plan = prepare_requests(cfg, model, section, text)
            replacements, records = {}, []
            for unit in units:
                assert plan.policy['design_grounding'], 'This recipe requires actual native unit grounding'
                store, _ = store_for(cfg, model, section, unit, plan.prompts[unit['id']],
                                     plan.policy['design_grounding'], answers)
                assert store is not None, 'This native recipe requires receipt-bound checkpoints'
                statements, record = _request_unit(
                    cfg, model, execution, section, unit, plan.prompts[unit['id']],
                    plan.policy['design_grounding'], None, answers)
                assert len(statements) == 1
                assert statements[0].get('part_id') == unit['_part_id']
                # The common request path validates and grounds before writing
                # this checkpoint. read() verifies its original native receipts.
                checked = store.read()
                assert checked is not None and checked[0]['statements'] == statements
                key = (unit['id'], unit['_part_id'])
                replacements[key] = statements[0]
                answers[unit['id']].extend(statements)
                records.append(dict(topic=key[0], part=key[1], native_record=record,
                                    action=('generated' if record is None else
                                            'reused-draft-new-grounding' if record.get('new_grounding_review') else
                                            'checkpoint-revalidated' if record.get('revalidated') else 'checkpoint-reused'),
                                    verified_checkpoint=str(store.path),
                                    checkpoint_sha256=hashlib.sha256(store.path.read_bytes()).hexdigest(),
                                    native_receipts=checked[0]['receipts']))
            # Restore the original display order, keeping every unaffected row exact.
            answers = {tid: [replacements.get((tid, row.get('part_id')), copy.deepcopy(row))
                             for row in rows] for tid, rows in old['answers'].items()}
            result = _assemble_generation(
                cfg, model, section, answers, copy.deepcopy(old['topic_inputs']),
                [tid for tid in answers if not any(t == tid for t, _ in wanted)], [],
                copy.deepcopy(old['topic_agents']), plan.policy)
            result.artifact['partial_revision'] = dict(
                changed_units=records,
                prior_manuscript_sha256=hashlib.sha256(before).hexdigest(),
                prior_revision=copy.deepcopy(old.get('partial_revision')),
                prior_grounding_review=old.get('grounding_review', 'not-run'),
                retained_topic_identities='Historical identities retained; no current-profile reuse promotion',
                retained_statement_count=sum(len(rows) for rows in answers.values()) - len(wanted),
                selected_unit_grounding_review='passed; may reuse historical grounding; see each unit action and native receipts',
                new_unit_agent=dict(runner=cfg.agent.runner, model=cfg.agent.model,
                                    command=cfg.agent.identity_command, args=cfg.agent.args),
                human_review='pending')
            # Only the selected units have a fresh source review. Original full
            # page results remain historical in the bound prior revision.
            result.artifact['grounding_review'] = 'not-run'
            result.artifact['grounding_policy'] = old.get('grounding_policy')
            generator = Generator(staged_cfg, model, execution)
            generator.generated_designs[sid] = result
            # These selected pages use source-bound configured figures, not new LLM graphs.
            assert not meta.get('generated_visuals'), 'Native figures require separate authenticated handling'
            written = generator._prose(section)
            after, _ = split_frontmatter(written.read_text(encoding='utf-8'))
            changed = [(tid, row.get('part_id')) for tid, rows in old['answers'].items()
                       for i, row in enumerate(rows) if after['generated_design']['answers'][tid][i] != row]
            assert len(changed) == len(set(changed)) and set(changed) <= wanted
            for tid, rows in old['answers'].items():
                assert len(after['generated_design']['answers'][tid]) == len(rows)
            for tid, pid in wanted:
                actual = next(row for row in after['generated_design']['answers'][tid]
                              if row.get('part_id') == pid)
                assert actual == replacements[(tid, pid)]
            results.append(dict(section=sid, changed_units=changed,
                                retained_statement_count=result.artifact['partial_revision']['retained_statement_count']))
            (output / 'completed-sections.json').write_text(json.dumps(
                dict(sections=results, generation_run=str(execution.path)),
                ensure_ascii=False, indent=2), encoding='utf-8')
    # All staged pages and unchanged rows passed before touching any source page.
    for rel, raw in originals.items():
        if (original_sdd / rel).read_bytes() != raw:
            raise ValueError('Source manuscript changed during staged generation: ' + str(rel))
    try:
        for rel in originals:
            shutil.copyfile(staged_cfg.sdd_dir / rel, original_sdd / rel)
        (output / 'result.json').write_text(json.dumps(dict(
            status='selected-native-units-repaired', results=results,
            source_commit=model.meta['source_commit'], human_review='pending'),
            ensure_ascii=False, indent=2), encoding='utf-8')
    except BaseException:
        for rel, raw in originals.items():
            (original_sdd / rel).write_bytes(raw)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--targets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repair(args.config, args.targets, args.out)
