"""Cheap publication gates and a source-bound plan before any long CLI call."""
from pathlib import Path
import hashlib
import json
import re

from .config import load, section_output
from .state_io import save
from .validation_stage import current, load_json, read_bytes, read_text
from .validation_execution import staged
from .publication_reports import check_reports


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
    options = cfg.publication
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
    rules.update(cfg.publication.get('shared_labels', {}))
    for source, rule in rules.items():
        value = strings.get(source)
        if not isinstance(value, str) or re.search(rule['reject'], value, re.I):
            raise ValueError('Publication shared-label regression: ' + source)
        if rule.get('require') and not re.search(rule['require'], value, re.I):
            raise ValueError('Publication shared-label term missing: ' + source)




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
    from .generation_run import observed
    execution = observed()
    contract = getattr(execution, 'publication_contract', None) if execution else None
    if contract:
        contract.select(model, [s['id'] for s in cfg.sections()
            if (not section_ids or s['id'] in section_ids) and (not impact or s['id'] in impact.sections)])
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
        pending = []
        for unit in _design_units(section, {}):
            key = _unit_tag(section, unit)
            dependencies = list(pending)
            reused = unit['id'] in retained
            action, reason, receipts = 'reuse-manuscript', 'source/request/model/style identical; current checks passed', []
            explanation = dict(reason_codes=['identical-manuscript-inputs-current-checks-passed'])
            if not reused:
                store, identity = store_for(cfg, model, section, unit, plan.prompts[unit['id']],
                                             plan.policy['design_grounding'], answers)
                cached = store.read() if store is not None else None
                action, reason = 'generate', 'no exact completed checkpoint or reusable manuscript'
                explanation = store.explain(cached) if store is not None else dict(reason_codes=['checkpoint-unavailable'])
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
                # A checkpoint's final outcome still belongs to execution.
                # Even a forecast hit can be rejected under current checks.
                pending.append(key)
            forecast = action
            if dependencies:
                # Earlier checkpoint/generation outcomes are not final yet.
                # Their duplicate/contract checks can reject an otherwise exact
                # later draft. Never publish a guessed final reuse verdict.
                action = 'resolve-after-dependencies'
                reason = 'earlier answers/reviews are pending; runtime must resolve current checks'
            units.append(dict(section=section['id'], topic=unit['id'], part=unit.get('_part_id'),
                subpart=unit.get('_subpart_id'), unit=key,
                question=unit['question'], input_sha256=plan.inputs[unit['id']],
                action=action, forecast=forecast, certainty='conditional' if dependencies else 'input-bound',
                depends_on=dependencies,
                reason=reason, receipts=receipts, explanation=explanation))
    inputs = current()
    inputs.verify()
    report = dict(schema=1, source_commit=model.meta.get('source_commit'),
        baseline=baseline, execution=dict(kind=cfg.agent.kind, runner=cfg.agent.runner,
        model=cfg.agent.model, args=cfg.agent.args, command=cfg.agent.identity_command),
        limits={key: getattr(cfg.review, key) for key in
                ('max_calls', 'max_seconds', 'document_max_calls', 'document_max_seconds')},
        sections=[s['id'] for s in selected], units=units, carryover=carryover,
        inputs=inputs.manifest(), human_review='pending')
    from .publication_operation import archive_plan
    archive_plan(cfg, report, execution)
    from .generation_run import observed
    execution = observed()
    if execution is not None:
        references = execution.report.get('publication_plans', [])
        execution.report['publication_plan'] = dict(
            path=references[-1]['path'] if references else str(cfg.build_dir/'publication-plan.json'),
            input_sha256=report['input_sha256'])
        for unit in units:
            execution.decision(unit['unit'], dict(action=unit['action'], stage='forecast',
                forecast=unit['forecast'], certainty=unit['certainty'], depends_on=unit['depends_on'],
                **unit['explanation']))
    from collections import Counter
    print('Publication plan: ' + str(cfg.build_dir/'publication-plan.json') + '; ' +
          ', '.join(f'{action}={count}' for action, count in sorted(Counter(u['action'] for u in units).items())))
    return report
