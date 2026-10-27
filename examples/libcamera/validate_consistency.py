"""Evaluate synthetic public-source contract cases through the selected CLI."""
from pathlib import Path
import argparse
import hashlib
import json

import yaml

from sdd.config import load
from sdd.consistency import SYSTEM, schema, validate
from sdd.facts.model import KnowledgeModel
from sdd.generation_run import Execution
from sdd.llm import Agent
from sdd.state_io import save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--cases', type=Path, default=Path(__file__).parent/'validation/consistency-cases.yaml')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = load(args.config)
    model = KnowledgeModel.load(cfg.facts_path)
    runner = Execution(cfg, Agent(cfg.agent, cfg.build_dir/'prompts'))
    cases = yaml.safe_load(args.cases.read_text(encoding='utf-8'))['cases']
    report = dict(schema=1, source_commit=model.meta['source_commit'], cases=[], human_review='pending',
                  scope='Synthetic evaluation statements, not published manuscript content; actual selected CLI calls.')
    for case in cases:
        sources = {}
        for sid in case['sources']:
            record = model.evidence[sid]
            excerpt = record.get('context', record)
            assert record['commit'] == model.meta['source_commit']
            assert hashlib.sha256(excerpt['text'].encode()).hexdigest() == excerpt['sha256']
            sources[sid] = dict(file=record['file'], line=excerpt['line'], text=excerpt['text'])
        expected = {key: row['expected'] for key, row in case['claims'].items()}
        claims = {key: {k: v for k, v in row.items() if k!='expected'} for key, row in case['claims'].items()}
        payload = dict(contract=dict(id=case['id'], primary='fixture', question='Compare the complete contract with its conditions and source.'),
                       source_commit=model.meta['source_commit'], claims=claims, sources=sources)
        raw = runner.chat(SYSTEM, json.dumps(payload, ensure_ascii=False),
                          tag='consistency_case_'+case['id'], response_schema=schema(payload))
        findings = validate(payload, raw)
        report['cases'].append(dict(id=case['id'], expected=expected, findings=findings,
                                    receipt=str(runner.last_receipt),
                                    correct=all(expected[row['claim_id']]==row['status'] for row in findings)))
        save(args.out, report, newline='\n')
        print(case['id'], [(r['claim_id'], r['status']) for r in findings], flush=True)
    rows = [(case['expected'][f['claim_id']], f['status']) for case in report['cases'] for f in case['findings']]
    report['metrics'] = dict(cases=len(cases), claims=len(rows), correct=sum(a==b for a,b in rows),
        contradictions=sum(a=='contradiction' for a,b in rows),
        detected=sum(a==b=='contradiction' for a,b in rows),
        missed=sum(a=='contradiction' and b!='contradiction' for a,b in rows),
        false_positives=sum(a!='contradiction' and b=='contradiction' for a,b in rows),
        compatible=sum(a=='compatible' for a,b in rows),
        undetermined=sum(b in ('ambiguous','insufficient-evidence') for a,b in rows))
    save(args.out, report, newline='\n')
    print(json.dumps(report['metrics']), flush=True)
    return 0 if all(case['correct'] for case in report['cases']) else 1


if __name__=='__main__':
    raise SystemExit(main())
