"""Repair a same-source trial with verified HTTP-response reuse and new calls.

This is explicitly a replay/repair, not a fresh full-model evaluation. Unchanged
requests keep their actual model responses; new requests go to the configured
provider. Manuscripts identify the response-bundle transport, and origin HTTP
receipts remain separate from replay receipts. Neither path grants approval.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time

from .config import load
from .evidence import collect
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def import_calls(seed, agent_cfg, destination, bundle):
    """Validate every seed before importing any; never prefer conflicting answers."""
    calls = seed / 'calls'
    if not calls.exists():
        calls = seed / 'prompts' / 'calls'
    records, unique = [], {}
    for path in sorted(calls.rglob('*.receipt.json')):
        prefix = str(path).removesuffix('.receipt.json')
        request_path, response_path = Path(prefix + '.request.json'), Path(prefix + '.response.txt')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        request = json.loads(request_path.read_text(encoding='utf-8'))
        response = response_path.read_text(encoding='utf-8')
        key = digest(json.dumps(request, ensure_ascii=False, sort_keys=True))
        if (receipt.get('http_call') is not True or receipt.get('transport') != agent_cfg.kind
                or receipt.get('model') != agent_cfg.model or receipt.get('request_sha256') != key
                or receipt.get('response_sha256') != digest(response)
                or any(receipt.get('settings', {}).get(k) != getattr(agent_cfg, k)
                       for k in ('temperature', 'think', 'num_ctx', 'max_output_tokens'))):
            raise ValueError(f'HTTP origin, request, response, model or settings mismatch: {path.name}')
        if key in unique and unique[key] != response:
            raise ValueError('Conflicting responses for the same request; select a non-conflicting seed.')
        unique[key] = response
        records.append((path, request_path, response_path))
    if not records:
        raise ValueError('The seed has no verified HTTP responses.')
    for paths in records:
        for path in paths:
            target = destination / path.relative_to(calls)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    bundle.mkdir(parents=True, exist_ok=True)
    for key, response in unique.items():
        (bundle / f'{key}.response.json').write_text(json.dumps(dict(
            schema=1, model=agent_cfg.model, request_sha256=key, response=response), ensure_ascii=False), encoding='utf-8')
    return len(unique)


def repair(cfg, seed, section_ids, out, *, agent_factory=Agent):
    if cfg.agent.kind not in ('ollama', 'openai-compatible'):
        raise ValueError('Repair requires a real model connection for changed requests.')
    sections = {s['id']: s for s in cfg.sections()}
    if not section_ids or any(s not in sections or sections[s].get('design_generation') != 'llm' for s in section_ids):
        raise ValueError('Select configured LLM design sections.')
    seed, out = seed.resolve(), out.resolve()
    protected = [cfg.root, cfg.source_root, cfg.sdd_dir, cfg.facts_dir, seed]
    if out.exists() or any(p.resolve().is_relative_to(out) for p in protected) or any(
            out.is_relative_to(p.resolve()) for p in protected[1:]):
        raise ValueError('Repair requires a new isolated output directory.')
    before = json.loads((seed / 'evaluation.json').read_text(encoding='utf-8'))
    model = KnowledgeModel.load(cfg.facts_path)
    if before['source_commit'] != model.meta['source_commit']:
        raise ValueError('This repair path requires the same source commit; use update for source changes.')
    out.mkdir(parents=True)
    bundle = out / 'responses'
    imported = import_calls(seed, cfg.agent, out / 'calls', bundle)
    trial = copy.deepcopy(cfg)
    snapshot = out / 'sections.yaml'
    snapshot.write_bytes(cfg.sections_file.read_bytes())
    trial.paths = {**trial.paths, 'sections_file': snapshot, 'scenarios_file': cfg.scenarios_file,
                   'prompts': cfg.prompts_dir, 'templates': cfg.templates_dir, 'style': cfg.style_dir}
    trial.root, trial.sdd_dir, trial.facts_dir = out, out / 'manuscripts', out / 'facts'
    trial.diagrams_dir = trial.sdd_dir / 'diagrams'
    trial.raw.setdefault('site', {})['enabled'] = False
    collect(trial, model)
    model.save(trial.facts_path)
    live = agent_factory(copy.deepcopy(cfg.agent), out / 'new-prompts')
    trial.agent.kind, trial.agent.response_dir = 'response-bundle', str(bundle)
    replay = Agent(trial.agent, out / 'replay-prompts')

    class RepairAgent:
        reused = 0
        def chat(self, system, user, tag='prompt', response_schema=None):
            request = dict(system=system, user=user, response_schema=response_schema)
            key = digest(json.dumps(request, ensure_ascii=False, sort_keys=True))
            path = bundle / f'{key}.response.json'
            if path.exists():
                self.reused += 1
            else:
                response = live.chat(system, user, tag=tag, response_schema=response_schema)
                path.write_text(json.dumps(dict(schema=1, model=cfg.agent.model,
                    request_sha256=key, response=response), ensure_ascii=False), encoding='utf-8')
            return replay.chat(system, user, tag=tag, response_schema=response_schema)

    agent, results = RepairAgent(), []
    for sid in section_ids:
        start = time.monotonic()
        try:
            paths = Generator(trial, model, agent).run([sid])
            results.append(dict(section=sid, automatic_checks='passed', manuscripts=[dict(
                path=p.relative_to(out).as_posix(), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]))
        except (ValueError, RuntimeError) as exc:
            results.append(dict(section=sid, automatic_checks='failed', error=str(exc)))
        results[-1]['elapsed_seconds'] = round(time.monotonic() - start, 2)
    if (out / 'new-prompts/calls').exists():
        shutil.copytree(out / 'new-prompts/calls', out / 'calls', dirs_exist_ok=True)
    report = dict(schema=1, source_commit=model.meta['source_commit'], provider=cfg.agent.kind, model=cfg.agent.model,
        execution_mode='verified-http-replay-and-live-repair', manuscript_agent='response-bundle/' + cfg.agent.model,
        seed_report_sha256=hashlib.sha256((seed / 'evaluation.json').read_bytes()).hexdigest(),
        imported_requests=imported, reused_responses=agent.reused, new_http_attempts=live._counter,
        new_http_calls=len(list((out / 'new-prompts/calls').rglob('*.receipt.json'))),
        settings={**{k: getattr(cfg.agent, k) for k in ('temperature', 'think', 'num_ctx', 'max_output_tokens')},
                  'max_retries': cfg.max_retries, 'design_prompt': cfg.raw.get('review', {}).get('design_prompt', 'standard')},
        sections_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        generator_files_sha256={n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
            for n in ('repair_reader.py', 'generated_design.py', 'evidence.py', 'focused_prompt.py', 'prompting.py')},
        results=results, semantic_review='pending', human_approval='pending', publishable=False,
        checks_scope='Exact HTTP provenance and configured checks, not a fresh full-model run or semantic approval.')
    (out / 'evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--section', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = repair(load(args.config), args.seed, args.section, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(r['automatic_checks'] == 'passed' for r in result['results']) else 1)
