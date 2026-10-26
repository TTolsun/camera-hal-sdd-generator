"""Bounded model diagnosis -> question/evidence proposal -> verified regeneration.

Runs only in an isolated directory. Never edits operational config, approves or
publishes manuscripts. Exact unchanged HTTP responses can be replayed with --seed.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import yaml

from .config import load
from .contract_schema import configuration_errors
from .evaluate_reader import evaluate
from .repair_reader import repair
from .evidence import collect
from .facts.model import KnowledgeModel
from .llm import Agent, AgentError
from . import reader_loop_policy as policy


class BudgetExceeded(Exception):
    """Bypass normal generation retries: exhausted budgets must stop immediately."""


@dataclass
class Limits:
    max_rounds: int = 3
    max_calls: int = 80
    max_seconds: int = 1800
    max_stalls: int = 2

    def validate(self):
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f'{name} must be a positive integer')


class Budget:
    def __init__(self, limits, clock=time.monotonic):
        self.limits, self.clock, self.calls = limits, clock, 0
        self.started = clock()

    def check(self):
        if self.clock() - self.started >= self.limits.max_seconds:
            raise BudgetExceeded('time_limit')

    def wrap(self, agent):
        budget = self
        class BoundedAgent:
            @property
            def _counter(self):
                return agent._counter

            def chat(self, system, user, **kwargs):
                budget.check()
                if budget.calls >= budget.limits.max_calls:
                    raise BudgetExceeded('call_limit')
                if len(system) + len(user) > agent.cfg.max_input_chars:
                    raise BudgetExceeded('input_limit')
                budget.calls += 1  # Failed HTTP attempts count too.
                agent.cfg.timeout_sec = min(agent.cfg.timeout_sec, max(1,
                    budget.limits.max_seconds - (budget.clock() - budget.started)))
                return agent.chat(system, user, **kwargs)
        return BoundedAgent()


def latest_response(trial, key):
    folder = trial / 'replay-prompts/calls'
    if not folder.exists():
        folder = trial / 'prompts/calls'
    prefix = key.replace('/', '_') + '_'
    found = []
    for path in folder.rglob('*.receipt.json'):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        # Numeric suffix avoids prefix collisions between topic/part IDs.
        if re.fullmatch(re.escape(prefix) + r'\d+(?:_revision)?', receipt['tag']):
            stem = str(path).removesuffix('.receipt.json')
            response = Path(stem + '.response.txt').read_text(encoding='utf-8')
            request = json.loads(Path(stem + '.request.json').read_text(encoding='utf-8'))
            from .repair_reader import digest
            if (receipt['response_sha256'] != digest(response)
                    or receipt['request_sha256'] != policy.digest(request)):
                raise ValueError('Trial response or request hash mismatch')
            found.append((receipt['completed_at'], receipt, response))
    return max(found, key=lambda item: item[0])[1:] if found else None


def automatic_error(cfg, model, unit, raw):
    """Use the production answer checks, independent of the model diagnosis."""
    from .generated_design import source_passages, resolve_passages, normalize_answer, validate_answers
    section, topic, part = unit
    topic = copy.deepcopy(topic)
    topic.pop('parts', None)
    if part:
        topic['question'] = part['question']
        topic['_part_id'] = part['id']
        topic['_max_statements'] = 1 if part.get('answer_contract') else 2
        topic['sources'] = [s for s in topic['sources'] if s['id'] in part['sources']]
        topic.pop('answer_contract', None)
        if 'answer_contract' in part:
            topic['answer_contract'] = part['answer_contract']
    sources = {s['id']: model.evidence[f"{section['id']}/{topic['id']}/{s['id']}"]['text'] for s in topic['sources']}
    _, passages = source_passages(sources,
        whole_source=cfg.raw.get('review', {}).get('design_prompt') == 'focused',
        scopes={s['id']: s['scope'] for s in topic['sources'] if 'scope' in s})
    try:
        data = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))
        if not isinstance(data, dict) or set(data) != {'statements'}:
            raise ValueError('Expected statements only')
        statements = resolve_passages(data['statements'], passages)
        if part:
            if len(statements) > (1 if part.get('answer_contract') else 2):
                raise ValueError('Too many statements for the part')
            for st in statements:
                st['part_id'] = part['id']
        normalize_answer(model, statements, [*sources.values(), topic['question']])
        subset = {**section, 'design_topics': [topic], 'design_requirements': [
            r for r in section['design_requirements'] if r['id'] in topic['covers']]}
        subset.pop('reader_profile', None)
        validate_answers(model, subset, {topic['id']: statements})
        return None
    except (ValueError, TypeError, KeyError) as exc:
        return str(exc)


def run(cfg, section_ids, out, *, seed=None, targets=None, limits=None, agent_factory=Agent):
    limits = limits or Limits()
    limits.validate()
    if cfg.agent.kind not in ('ollama', 'openai-compatible'):
        raise ValueError('The loop requires an actual local or internal model connection')
    original = cfg.sections()
    selected = [s for s in original if s['id'] in section_ids]
    if (not section_ids or len(set(section_ids)) != len(section_ids) or len(selected) != len(section_ids)
            or any(s.get('design_generation') != 'llm' for s in selected)):
        raise ValueError('Select unique configured LLM sections')
    all_units = policy.units(original, section_ids)
    targets = list(all_units) if targets is None else targets
    if not targets or len(set(targets)) != len(targets) or any(k not in all_units for k in targets):
        raise ValueError('Targets must name unique configured section/topic[/part] units')
    scopes = cfg.raw.get('review', {}).get('reader_loop', {}).get('evidence_scopes', {})
    if not isinstance(scopes, dict):
        raise ValueError('reader_loop.evidence_scopes must be a mapping')
    known_sources = {f"{s['id']}/{t['id']}/{r['id']}" for s in original
                     for t in s.get('design_topics', []) for r in t.get('sources', [])}
    if set(scopes) - known_sources:
        raise ValueError('Unknown evidence scope keys')
    out = Path(out).resolve()
    seed = Path(seed).resolve() if seed else None
    protected = [cfg.root, cfg.source_root, cfg.sdd_dir, cfg.facts_dir] + ([seed] if seed else [])
    if (out.exists() or any(p.resolve().is_relative_to(out) for p in protected)
            or any(out.is_relative_to(p.resolve()) for p in protected[1:])):
        raise ValueError('The loop needs a new isolated output directory')
    model = KnowledgeModel.load(cfg.facts_path)
    commit = model.meta['source_commit']
    if seed:
        prior = json.loads((seed/'evaluation.json').read_text(encoding='utf-8'))
        if prior['source_commit'] != commit:
            raise ValueError('Source commit changed; use the update workflow')
    # Resolve assets before changing sections/output paths.
    current = copy.deepcopy(cfg)
    current.paths = {**cfg.paths, 'prompts': cfg.prompts_dir, 'templates': cfg.templates_dir,
                     'style': cfg.style_dir, 'scenarios_file': cfg.scenarios_file}
    document = yaml.safe_load(cfg.sections_file.read_text(encoding='utf-8'))
    sections = copy.deepcopy(original)
    inputs = [cfg.sections_file, cfg.facts_path, *cfg.prompts_dir.glob('*.md'), *cfg.style_dir.glob('*.md')]
    inputs += [Path(__file__).with_name(name) for name in (
        'reader_loop.py', 'reader_loop_policy.py', 'repair_reader.py', 'evaluate_reader.py',
        'generated_design.py', 'generated_visuals.py', 'evidence.py', 'answer_contracts.py')]
    def input_hashes():
        return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    initial_hashes = input_hashes()
    def check_inputs():
        if input_hashes() != initial_hashes:
            raise BudgetExceeded('inputs_changed')
    out.mkdir(parents=True)
    budget = Budget(limits)
    factory = lambda settings, dump: budget.wrap(agent_factory(settings, dump))
    report = dict(schema=1, source_commit=commit, model=cfg.agent.model, provider=cfg.agent.kind,
        limits=vars(limits), original_sections_sha256=policy.digest(original), targets=targets,
        input_files_sha256=initial_hashes,
        excluded_units=sorted(set(all_units)-set(targets)), rounds=[], stop_reason=None,
        semantic_review='model-only; human review pending', independent_review=False,
        human_approval='pending', publishable=False,
        scope='Prose answer diagnosis only. Graphs retain production checks and require separate semantic review.')
    seen, reviews, failures = {policy.digest(sections)}, {}, {}
    try:
        for number in range(1, limits.max_rounds + 1):
            budget.check()
            check_inputs()
            directory = out/f'round-{number:02d}'
            directory.mkdir()
            snapshot = directory/'sections.yaml'
            snapshot.write_text(yaml.safe_dump({**document, 'sections': sections}, allow_unicode=True,
                                               sort_keys=False), encoding='utf-8')
            current.paths['sections_file'] = snapshot
            collect(current, model)
            mapping = policy.units(sections, section_ids)
            pools = {key: policy.candidates(current, model, key, mapping[key], scopes) for key in targets}
            entry = dict(round=number, sections_sha256=policy.digest(sections), reviews=[], edits=[])
            report['rounds'].append(entry)
            trial = directory/'trial'
            evaluation = (repair(current, seed, section_ids, trial, agent_factory=factory) if seed
                          else evaluate(current, section_ids, trial, agent_factory=factory))
            entry['evaluation'] = str((trial/'evaluation.json').relative_to(out))
            entry['automatic_passed'] = all(r['automatic_checks'] == 'passed' for r in evaluation['results'])
            entry['generation'] = {k:evaluation[k] for k in
                ('execution_mode', 'reused_responses', 'new_http_attempts', 'new_http_calls') if k in evaluation}
            draft_sections = copy.deepcopy(sections)
            completed, unresolved = 0, False
            critic = factory(copy.deepcopy(cfg.agent), directory/'diagnosis-prompts')
            for key in targets:
                budget.check()
                response = latest_response(trial, key)
                if not response:
                    entry['reviews'].append(dict(target=key, status='not_reached'))
                    continue
                receipt, raw = response
                section, topic, part = mapping[key]
                old_section, old_topic, old_part = all_units[key]
                error = automatic_error(current, model, mapping[key], raw)
                pool = pools[key]
                current_pool = {k:v for k,v in pool.items() if k.endswith(':current')}
                gaps, required_expansions = policy.incomplete_expressions(pool)
                try:
                    decoded_answer = json.loads(raw)['statements']
                    answer_text = [st['text'] for st in decoded_answer]
                except (ValueError, TypeError, KeyError):
                    answer_text = raw
                answer_contract = (part or topic).get('answer_contract')
                found_terms = [[term for term in group if term in str(answer_text)]
                               for group in (answer_contract or {}).get('required_terms', [])]
                payload = dict(original_question=(old_part or old_topic)['question'],
                    current_question=(part or topic)['question'], answer_contract=answer_contract,
                    answer=answer_text, required_terms_found=found_terms, automatic_error=error, evidence_gaps=gaps,
                    candidates={k: {f:v for f,v in c.items() if f != 'selector'} for k,c in current_pool.items()})
                review_key = policy.digest({'policy': policy.DIAGNOSIS_POLICY,
                                            'schema': policy.schema(current_pool), 'payload': payload})
                reused = review_key in reviews
                if reused:
                    proposal = reviews[review_key]
                else:
                    # Compatible gateways may ignore response_schema; keep the
                    # same portable JSON contract in their textual request too.
                    user = json.dumps({**payload, 'output_schema': policy.schema(current_pool)}, ensure_ascii=False)
                    raw_review = critic.chat(policy.DIAGNOSIS_POLICY, user, tag='diagnose_' + key.replace('/', '_'),
                        response_schema=policy.schema(current_pool))
                    proposal = policy.decode(raw_review, current_pool)
                    reviews[review_key] = proposal
                record = dict(target=key, response_sha256=receipt['response_sha256'],
                    request_sha256=receipt['request_sha256'], automatic_error=error,
                    review_key=review_key, reused_review=reused, diagnosis=proposal)
                entry['reviews'].append(record)
                if proposal['verdict'] != 'acceptable' or gaps:
                    planning = {**payload, 'diagnosis': proposal,
                        'candidates': {k:{f:v for f,v in c.items() if f != 'selector'} for k,c in pool.items()},
                        'required_expansions': required_expansions,
                        'output_schema': policy.schema(pool)}
                    plan_user = json.dumps(planning, ensure_ascii=False)
                    for attempt in range(cfg.max_retries + 1):
                        raw_plan = critic.chat(policy.PLANNING_POLICY, plan_user,
                            tag=f"plan_{key.replace('/', '_')}_{attempt}", response_schema=policy.schema(pool))
                        try:
                            proposal = policy.decode(raw_plan, pool)
                            if proposal['verdict'] == 'acceptable':
                                raise ValueError('A plan cannot approve an answer before regeneration')
                            if proposal['verdict'] == 'repair' and not set(required_expansions) <= set(proposal['expand']):
                                raise ValueError('Repair must select required_expansions: ' + repr(required_expansions))
                            break
                        except ValueError as exc:
                            if attempt == cfg.max_retries:
                                raise
                            plan_user = json.dumps(planning, ensure_ascii=False) + '\nRejected proposal (not evidence):\n' + raw_plan + '\nCorrection: ' + str(exc)
                    record['plan_attempts'] = attempt + 1
                record['proposal'] = proposal
                if proposal['verdict'] == 'insufficient_evidence':
                    report['stop_reason'] = 'insufficient_evidence'
                    break
                if proposal['verdict'] == 'acceptable':
                    failures.pop(key, None)
                    completed += not bool(error)
                    unresolved |= bool(error)
                    continue
                signature = policy.digest(sorted((f['category'], pool[f['candidate']]['source'], f['quote'])
                                                  for f in proposal['findings']))
                previous, count = failures.get(key, (None, 0))
                failures[key] = (signature, count + 1 if signature == previous else 1)
                if failures[key][1] >= limits.max_stalls:
                    report['stop_reason'] = 'repeated_failure'
                    break
                draft_sections = policy.apply(draft_sections, key, proposal, pool)
                entry['edits'].append(key)
            if report['stop_reason']:
                break
            if completed == len(targets) and entry['automatic_passed']:
                report['stop_reason'] = 'model_review_complete'
                report['candidate_trial'] = str(trial.relative_to(out))
                break
            if unresolved:
                report['stop_reason'] = 'unresolved_automatic_failure'
                break
            fingerprint = policy.digest(draft_sections)
            if fingerprint in seen:
                report['stop_reason'] = ('unreached_targets' if any(
                    r.get('status') == 'not_reached' for r in entry['reviews']) else 'no_progress')
                break
            for section in draft_sections:
                errors = configuration_errors(section)
                if errors:
                    raise ValueError('Proposal violates original configuration: ' + ' / '.join(errors))
            seen.add(fingerprint)
            entry['proposed_sections_sha256'] = fingerprint
            (directory/'proposed-sections.yaml').write_text(yaml.safe_dump(
                {**document, 'sections': draft_sections}, allow_unicode=True, sort_keys=False), encoding='utf-8')
            if number == limits.max_rounds:
                report['stop_reason'] = 'round_limit'
                break
            sections, seed = draft_sections, trial
        budget.check()
        check_inputs()
    except BudgetExceeded as exc:
        report['stop_reason'] = str(exc)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, AgentError) as exc:
        report['stop_reason'], report['error'] = 'invalid_or_unavailable', str(exc)
    except KeyboardInterrupt:
        report['stop_reason'] = 'interrupted'
    finally:
        report['http_attempts'] = budget.calls
        report['elapsed_seconds'] = round(budget.clock()-budget.started, 2)
        if report['stop_reason'] != 'model_review_complete':
            report.pop('candidate_trial', None)
        (out/'loop.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--section', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--target', action='append', help='Optional section/topic[/part]; report remaining units as excluded')
    for name, value in vars(Limits()).items():
        parser.add_argument('--'+name.replace('_', '-'), type=int, default=value)
    args = parser.parse_args()
    report = run(load(args.config), args.section, args.out, seed=args.seed, targets=args.target,
                 limits=Limits(**{k:getattr(args,k) for k in vars(Limits())}))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['stop_reason'] == 'model_review_complete' else 1)


if __name__ == '__main__':
    main()
