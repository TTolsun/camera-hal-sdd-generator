"""Run configured LLM contracts in isolation; never approve or publish a trial.

python -m sdd.evaluate_reader --config project/sdd.yaml --section overview --out trial
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from .config import load
from .evidence import collect
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent, LIVE_KINDS
from .trial_workspace import clone_config, validate_output, write_snapshot


def evaluate(cfg, section_ids, out: Path, *, agent_factory=Agent):
    if cfg.agent.kind not in LIVE_KINDS:
        raise ValueError('모델 자동 생성 시험에는 실제 CLI 또는 명시적으로 허용한 API 연결이 필요합니다.')
    sections = {s['id']: s for s in cfg.sections()}
    if not section_ids or any(s not in sections or sections[s].get('design_generation') != 'llm'
                              for s in section_ids):
        raise ValueError('시험할 LLM 설계 섹션을 명시해야 합니다.')
    try:
        out = validate_output(cfg, out)
    except ValueError as exc:
        raise ValueError(f'평가 출력에는 기존 입력·원고를 포함하지 않는 새 디렉터리가 필요합니다. {exc}') from exc
    out.mkdir(parents=True)
    sections_bytes = cfg.sections_file.read_bytes()
    sections_hash = hashlib.sha256(sections_bytes).hexdigest()
    (out/'sections.yaml').write_bytes(sections_bytes)
    generator_hashes = {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ('generated_design.py','focused_prompt.py','prompting.py','evidence.py',
                                    'answer_contracts.py','contract_schema.py','evaluate_reader.py','validate.py',
                                    'trial_workspace.py')}
    trial = clone_config(cfg, out, sections_file=out/'sections.yaml')
    write_snapshot(trial, out/'sdd.yaml')
    model = KnowledgeModel.load(cfg.facts_path)
    collect(trial, model)
    model.save(trial.facts_path)
    agent = agent_factory(trial.agent, out / 'prompts')
    results = []
    for sid in section_ids:
        start = time.monotonic()
        try:
            paths = Generator(trial, model, agent).run([sid])
            results.append({'section':sid,'automatic_checks':'passed',
                            'manuscripts':[{ 'path':p.relative_to(out).as_posix(),
                              'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})
        except (ValueError, RuntimeError) as exc:
            results.append({'section':sid,'automatic_checks':'failed','error':str(exc)})
        results[-1]['elapsed_seconds'] = round(time.monotonic()-start, 2)
    report = {'schema':1, 'source_commit':model.meta['source_commit'],
              'model':trial.agent.model, 'provider':trial.agent.kind,
              'settings':{'temperature':trial.agent.temperature,'num_ctx':trial.agent.num_ctx,
                          'think':trial.agent.think,
                          'max_output_tokens':trial.agent.max_output_tokens,
                          'max_retries':trial.max_retries,
                          'design_prompt':trial.raw.get('review',{}).get('design_prompt','standard'),
                          'design_revision':bool(trial.raw.get('review',{}).get('design_revision',False))},
              'sections_sha256':sections_hash,
              'generator_files_sha256':generator_hashes,
              'checks_scope':'Coverage, source binding, configured terms and known textual failure patterns; not a semantic truth oracle.',
              'results':results, 'semantic_review':'pending', 'human_approval':'pending',
              'publishable':False,
              'review_questions':['주장마다 직접 근거와 적용 조건을 찾을 수 있습니까?',
                                  '제공 기능을 측정 성능이나 지원 보장으로 바꾸지 않았습니까?',
                                  '연동 순서·책임·실패 조건이 빠지거나 뒤바뀌지 않았습니까?',
                                  '미지원과 미검증, 참고 측정과 제품 시험을 구분합니까?']}
    (out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--section', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(load(args.config), args.section, args.out)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if all(r['automatic_checks']=='passed' for r in report['results']) else 1)


if __name__ == '__main__':
    main()
