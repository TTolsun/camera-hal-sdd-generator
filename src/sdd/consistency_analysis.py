"""Typed evidence for a scenario view's analysis limits, never device behavior."""
from __future__ import annotations

import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent
PREFIX = '@analysis/scenario/'


def definitions():
    rows = []
    for relative, names in [('facts/model.py', {'Message', 'Scenario'}),
                            ('facts/callgraph.py', {'_deferred_targets', 'trace'}),
                            ('scenario_document.py', {'build'})]:
        path = ROOT/relative
        text = path.read_text(encoding='utf-8')
        for node in ast.parse(text).body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef)) or node.name not in names:
                continue
            # The renderer's declared representation contract, not its output
            # warning string, accompanies the actual extractor implementation.
            selected = node.body[0] if relative == 'scenario_document.py' else node
            start = min([selected.lineno, *[d.lineno for d in getattr(selected, 'decorator_list', [])]])
            excerpt = '\n'.join(text.splitlines()[start-1:selected.end_lineno])
            rows.append(dict(file='src/sdd/'+relative, name=node.name, line=start,
                text=excerpt, sha256=hashlib.sha256(excerpt.encode()).hexdigest()))
    if len(rows) != 5:
        raise ValueError('Scenario analysis definitions are incomplete')
    return rows


def evidence(model, sid):
    if not sid.startswith(PREFIX) or sid[len(PREFIX):] not in model.scenarios:
        raise ValueError('Unknown scenario analysis evidence')
    scenario = model.scenarios[sid[len(PREFIX):]]
    data = dict(kind='analysis-definition', project_source_commit=model.meta['source_commit'],
        scope='Analysis representation only; not product runtime, hardware or callback-thread evidence.',
        scenario=dict(id=scenario.id, entry=scenario.entry, messages_total=len(scenario.messages),
            unresolved=scenario.unresolved, deferred=scenario.deferred,
            annotated_messages=[asdict(row) for row in scenario.messages if row.note]),
        generator_definitions=definitions())
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return dict(kind='analysis-definition', file=sid, line=1, text=text,
                sha256=hashlib.sha256(text.encode()).hexdigest())


def paragraph_refs(cfg, model, meta, paragraph):
    bound = any(s.get('scenario') == meta.get('scenario_id') and s['id'] == meta.get('section')
                for s in cfg.sections() if s.get('scenario'))
    if meta.get('generation_method') != 'extracted-scenario' and not bound:
        return []
    scenario_id = meta.get('scenario_id')
    if scenario_id not in model.scenarios:
        raise ValueError('Scenario document has no matching extraction')
    from .scenario_document import fingerprint
    settings = next((row for row in cfg.scenarios() if row['id'] == scenario_id), {})
    scenario = model.scenarios[scenario_id]
    if (meta.get('entry') != scenario.entry
            or meta.get('scenario_fingerprint') != fingerprint(scenario, settings)):
        raise ValueError('Scenario analysis fingerprint mismatch')
    # Recognize only the renderer's exact constant note, not arbitrary prose
    # that happens to mention a scenario or a keyword about analysis.
    tree = ast.parse((ROOT/'scenario_document.py').read_text(encoding='utf-8'))
    if any(isinstance(node, ast.Constant) and isinstance(node.value, str)
           and len(node.value) >= 32 and node.value.strip() == paragraph.strip()
           for node in ast.walk(tree)):
        return [PREFIX+scenario_id]
    return []
