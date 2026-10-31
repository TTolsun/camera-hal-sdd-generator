"""Cheap publication gates and a source-bound plan before any long CLI call."""
from pathlib import Path
import hashlib
import json
import re

from .config import load, section_output
from .state_io import save
from .validation_stage import staged, current, load_json, read_bytes, read_text


def _requirements(sections):
    """Capture required questions/summary units/terms and every output owner."""
    result = {}
    for section in sections:
        sid = section['id']
        result[f'{sid}/output'] = section_output(section)
        for requirement in section.get('design_requirements', []):
            result[f"{sid}/requirement/{requirement['id']}"] = requirement
        for topic in section.get('design_topics', []):
            for owner in [topic, *topic.get('parts', [])]:
                key = f"{sid}/{topic['id']}/{owner.get('id', 'topic')}"
                if owner.get('role') == 'summary':
                    result[key+'/summary'] = owner
                terms = owner.get('answer_contract', {}).get('required_terms')
                if terms:
                    result[key+'/terms'] = terms
    return result


def check_baseline(cfg):
    options = cfg.raw.get('publication') or {}
    if not options.get('baseline_config'):
        return None
    baseline = load(cfg.root/options['baseline_config'])
    current().pin(baseline)
    expected = _requirements(baseline.sections())
    actual = _requirements(cfg.sections())
    from .glossary import load as load_glossary
    expected_terms, actual_terms = load_glossary(baseline), load_glossary(cfg)
    if expected_terms.configured and expected_terms.known() - actual_terms.known():
        raise ValueError('Publication profile lost baseline glossary terms: ' +
                         ', '.join(sorted(expected_terms.known() - actual_terms.known())))
    allowed = options.get('allowed_contract_changes', {})
    if (not isinstance(allowed, dict) or any(not isinstance(reason, str) or not reason.strip()
                                            for reason in allowed.values())):
        raise ValueError('Allowed contract changes require explicit per-key reasons')
    changes = [key for key, value in expected.items() if actual.get(key) != value and key not in allowed]
    if changes:
        raise ValueError('Publication profile lost baseline contracts: ' + ', '.join(changes))
    return dict(path=str(cfg.root/options['baseline_config']), allowed_contract_changes=allowed)


def check_catalog(cfg):
    if not cfg.site.english_catalog:
        return
    path = cfg.root/cfg.site.english_catalog
    if not path.is_file():
        return  # Initial translation output is allowed to be absent before drafting.
    catalog = load_json(path)
    strings = catalog.get('strings', {})
    if not isinstance(strings, dict):
        raise ValueError('Publication catalog strings must be an object')
    for source, translated in strings.items():
        if not translated:
            continue  # New units remain explicit translation work, never a pass.
        placeholders = re.findall(r'\{\{\d+\}\}', source)
        if sorted(placeholders) != sorted(re.findall(r'\{\{\d+\}\}', translated)):
            raise ValueError('Publication translation placeholders changed: ' + source)
    # Project-owned terminology assertions apply to exact shared keys, not to
    # arbitrary runtime sentences or a hardcoded public project's vocabulary.
    rules = {key: dict(require=r'\bsection\b', reject=r'\bclause\b') for key in strings
             if key.startswith('절 전체 근거')}
    rules.update((cfg.raw.get('publication') or {}).get('shared_labels', {}))
    for source, rule in rules.items():
        value = strings.get(source)
        if not isinstance(value, str) or re.search(rule['reject'], value, re.I):
            raise ValueError('Publication shared-label regression: ' + source)
        if rule.get('require') and not re.search(rule['require'], value, re.I):
            raise ValueError('Publication shared-label term missing: ' + source)


def check_reports(cfg, gate):
    """Require declared reports at their producing boundary, before copying."""
    checked = []
    for row in (cfg.raw.get('publication') or {}).get('reports', []):
        if not all(row.get(key) for key in ('path', 'gate', 'producer', 'sha256', 'bindings')):
            raise ValueError('Publication reports need path/gate/producer/sha256/bindings')
        if row['gate'] != gate:
            continue
        path = cfg.root/row['path']
        raw = read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Publication report hash mismatch: ' + row['path'])
        data = load_json(path)
        if any(data.get(key) != value for key, value in row['bindings'].items()):
            raise ValueError('Publication report stage/input/status mismatch: ' + row['path'])
        checked.append(dict(**row, verified=True))
    return checked


@staged
def prepare(cfg, model, section_ids=None, impact=None):
    from . import generated_design
    from .design_request import prepare_requests, _design_units
    from .design_reuse import reusable
    from .design_response import _validate_retained
    from .design_checkpoint import store_for, changes
    from .design_execution import _validate_unit_response
    from .design_request import _unit_request, _unit_tag
    from . import duplicates
    baseline = check_baseline(cfg)
    check_catalog(cfg)
    check_reports(cfg, 'before-generation')
    selected, units, carryover = [], [], []
    for section in cfg.sections():
        if ((section_ids and section['id'] not in section_ids)
                or (impact and section['id'] not in impact.sections)):
            carryover.append(dict(section=section['id'], document=section_output(section),
                                  reason='outside selected impact; current evidence must be revalidated'))
            continue
        selected.append(section)
        if not generated_design.enabled(section):
            continue
        from .design_response import preflight
        preflight(model, section)
        path = cfg.sdd_dir/section_output(section)
        previous = read_text(path) if impact and path.exists() else None
        plan = prepare_requests(cfg, model, section, previous)
        retained, _ = reusable(model, section, plan.previous, plan.inputs, _validate_retained)
        for tid in duplicates.repeated_topics(model, section, retained):
            retained.pop(tid)
        answers = {tid: list(values) for tid, values in retained.items()}
        for unit in _design_units(section, {}):
            reused = unit['id'] in retained
            action, reason, receipts = 'reuse-manuscript', 'source/request/model/style identical; current checks passed', []
            if not reused:
                store, identity = store_for(cfg, model, section, unit, plan.prompts[unit['id']],
                                             plan.policy['design_grounding'], answers)
                cached = store.read() if store is not None else None
                action, reason = 'generate', 'no exact completed checkpoint or reusable manuscript'
                if cached is not None:
                    saved, reviewer = cached
                    request = _unit_request(model, section, unit, plan.prompts[unit['id']][0])
                    grounding_changed, changed = changes(saved['identity'], identity)
                    try:
                        statements = _validate_unit_response(cfg, model, reviewer, section, unit,
                            saved['raw'], request.sources, request.passages, _unit_tag(section, unit),
                            plan.policy['design_grounding'] and not grounding_changed,
                            request.source_files, request.scopes, request.context_records, prior_answers=answers)
                    except (ValueError, KeyError, TypeError):
                        if not (changed or grounding_changed):
                            raise
                        action, reason = 'generate', 'completed draft rejected under changed current validation'
                    else:
                        answers.setdefault(unit['id'], []).extend(statements)
                        receipts = saved['receipts']
                        action = 'review-existing' if grounding_changed else 'revalidate-checkpoint' if changed else 'reuse-checkpoint'
                        reason = ('grounding policy changed; new automatic review required' if grounding_changed else
                                  'completed receipt-bound draft passes current checks; original provenance retained')
            units.append(dict(section=section['id'], topic=unit['id'], part=unit.get('_part_id'),
                question=unit['question'], input_sha256=plan.inputs[unit['id']],
                action=action, reason=reason, receipts=receipts))
    inputs = current()
    inputs.verify()
    report = dict(schema=1, source_commit=model.meta.get('source_commit'),
        baseline=baseline, execution=dict(kind=cfg.agent.kind, runner=cfg.agent.runner,
        model=cfg.agent.model, args=cfg.agent.args, command=cfg.agent.identity_command),
        limits={key: getattr(cfg.review, key) for key in
                ('max_calls', 'max_seconds', 'document_max_calls', 'document_max_seconds')},
        sections=[s['id'] for s in selected], units=units, carryover=carryover,
        inputs=inputs.manifest(), human_review='pending')
    report['input_sha256'] = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    save(cfg.build_dir/'publication-plan.json', report, newline='\n')
    return report
