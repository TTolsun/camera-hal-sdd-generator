"""Exercise every configured document and the site with a real model, in isolation.

The report records failures as they happen. An incomplete trial cannot build a
site, approve prose, publish, or replace operational manuscripts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time

from .config import load, section_output
from .document_health import enforce, page_path
from .document_metadata import split_frontmatter as _split
from .evidence import collect
from .export_site import export_site
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent, LIVE_KINDS
from .site_build import verify_site
from .state_io import save as save_state
from .trial_workspace import clone_config, contained_path, reject_symlinks, validate_output, write_snapshot


def evaluate(cfg, out: Path, *, translate: bool = False, previous: Path | None = None):
    if cfg.agent.kind not in LIVE_KINDS:
        raise ValueError('전체 생성 시험에는 실제 CLI 또는 명시적으로 허용한 모델 API 연결이 필요합니다.')
    if cfg.agent.kind != 'cli' and not cfg.agent.allow_direct_api:
        raise ValueError('직접 모델 API 시험에는 allow_direct_api: true를 명시해야 합니다.')
    if cfg.agent.kind == 'cli' and previous is not None:
        raise ValueError('CLI 전체 시험은 재개를 지원하지 않습니다. --continue-from 없이 새 시험을 실행하세요.')
    try:
        out = validate_output(cfg, out, previous=[previous] if previous else [])
    except ValueError as exc:
        raise ValueError(f'시험 출력에는 기존 입력·원고를 포함하지 않는 새 디렉터리가 필요합니다. {exc}') from exc
    if previous:
        previous = reject_symlinks(previous).resolve()
    out.mkdir(parents=True)
    sections_snapshot = out / 'sections.yaml'
    sections_snapshot.write_bytes(cfg.sections_file.read_bytes())
    trial = clone_config(cfg, out, sections_file=sections_snapshot)
    previous_catalog = cfg.site.english_catalog
    if previous_catalog:
        trial.raw['site']['english_catalog'] = str(out / 'english.json')
    write_snapshot(trial, out / 'sdd.yaml')
    report = {
        'schema': 1, 'source_commit': None, 'provider': cfg.agent.kind, 'model': cfg.agent.model,
        'runner': cfg.agent.runner if cfg.agent.kind == 'cli' else None,
        'model_selection': 'cli-default' if cfg.agent.kind == 'cli' and not cfg.agent.model else 'explicit',
        'agent_label': cfg.agent.label,
        'sections_sha256': hashlib.sha256(sections_snapshot.read_bytes()).hexdigest(),
        'engine_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(Path(__file__).parent.glob('*.py'))},
        'settings': {key: getattr(cfg.agent, key) for key in
                     ('max_input_chars', 'num_ctx', 'max_output_tokens', 'temperature', 'think')},
        'results': [], 'stages': [], 'semantic_review': 'pending',
        'human_approval': 'pending', 'publishable': False,
        'mode': 'repair' if previous else 'fresh',
    }

    def save():
        save_state(out / 'evaluation.json', report)

    def stage(name, action):
        start = time.monotonic()
        print(f'{name}: running', flush=True)
        try:
            result = action()
            record = {'stage': name, 'status': 'passed'}
            if isinstance(result, dict):
                record['result'] = result
        except Exception as exc:
            record = {'stage': name, 'status': 'failed', 'error': str(exc), 'error_type': type(exc).__name__}
        record['elapsed_seconds'] = round(time.monotonic() - start, 2)
        report['stages'].append(record)
        save()
        print(f'{name}: {record["status"]}', flush=True)
        return record['status'] == 'passed'

    save()
    model = None

    def configuration():
        sections = trial.sections()
        outputs = [section_output(section) for section in sections]
        if any(section.get('kind') == 'per-scenario' for section in sections):
            outputs += [f"scenarios/{scenario['id']}.md" for scenario in trial.scenarios()]
        for output in outputs:
            page_path(trial, output)
        if len(outputs) != len(set(outputs)):
            raise ValueError('Multiple sections would overwrite the same trial document')
        return {'sections': len(sections), 'outputs': len(outputs)}

    if not stage('configuration', configuration):
        return report

    def evidence():
        nonlocal model
        model = KnowledgeModel.load(cfg.facts_path)
        collect(trial, model)
        model.save(trial.facts_path)
        report['source_commit'] = model.meta['source_commit']
        report['facts_sha256'] = hashlib.sha256(trial.facts_path.read_bytes()).hexdigest()
        return {'structural_facts': 'reused', 'source_excerpts': len(model.evidence)}

    if not stage('evidence', evidence):
        return report
    if previous:
        def resume():
            old_bytes = contained_path(previous, 'evaluation.json').read_bytes()
            old = json.loads(old_bytes)
            expected = {s['id'] for s in trial.sections()}
            recorded = [row['section'] for row in old.get('results', [])]
            if (old.get('schema') != 1 or old.get('source_commit') != model.meta['source_commit']
                    or old.get('provider') != trial.agent.kind or old.get('model') != trial.agent.model
                    or not recorded or len(set(recorded)) != len(recorded) or not set(recorded) <= expected):
                raise ValueError('같은 소스·모델의 섹션 결과가 하나 이상 기록된 이전 시험만 재개할 수 있습니다.')
            for name in ('manuscripts', 'build/prompts/calls'):
                source = previous / name
                reject_symlinks(source, recursive=True)
            verified = []
            for row in old['results']:
                if row['automatic_checks'] != 'passed':
                    continue
                for item in row['manuscripts']:
                    source = contained_path(previous, item['path'])
                    if (not source.is_relative_to((previous / 'manuscripts').resolve())
                            or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']):
                        raise ValueError('이전 시험 원고가 기록된 해시와 다릅니다.')
                    meta, _ = _split(source.read_text(encoding='utf-8'))
                    if meta.get('generated_design') and any(
                            value != f'{trial.agent.kind}/{trial.agent.model}'
                            for value in meta['generated_design'].get('topic_agents', {}).values()):
                        raise ValueError('이전 원고의 모델 작성자가 시험 설정과 다릅니다.')
                    verified.append(source)
            # A crash may leave a file before its result was atomically recorded.
            # Only hash-checked, recorded manuscripts can be reused.
            for source in verified:
                target = trial.sdd_dir / source.relative_to(previous / 'manuscripts')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            from .provenance import verify_calls
            prior_authorship = verify_calls(model, trial.sdd_dir, previous / 'build/prompts/calls',
                                             provider=trial.agent.kind, model_name=trial.agent.model,
                                             allow_reused=True)
            for name, destination in [('build/prompts/calls', trial.build_dir / 'prompts/calls'),
                                      ('build/translation-prompts/calls', trial.build_dir / 'translation-prompts/calls')]:
                source = previous / name
                if source.exists():
                    reject_symlinks(source, recursive=True)
                    shutil.copytree(source, destination, dirs_exist_ok=True)
            report['continued_from_sha256'] = hashlib.sha256(old_bytes).hexdigest()
            return {'previous_results': len(old['results']), 'source_commit': old['source_commit'],
                    'previous_generation_complete': set(recorded) == expected,
                    'previous_authorship': prior_authorship}
        if not stage('resume-input', resume):
            return report
    agent = Agent(trial.agent, trial.build_dir / 'prompts')
    for section in trial.sections():
        sid = section['id']

        def generate():
            impact = None
            if previous:
                from .impact import ImpactReport
                impact = ImpactReport(base=model.meta['source_commit'], head=model.meta['source_commit'],
                    sections={sid: ['full repair trial']}, packages=list(model.packages),
                    scenarios={key: ['full repair trial'] for key in model.scenarios})
            paths = Generator(trial, model, agent, replay_http=bool(previous), all_design_units=True).run(
                [sid], **({'impact': impact} if impact else {}))
            if section.get('kind') == 'per-scenario':
                expected = {section_output(section), *[f"scenarios/{s['id']}.md" for s in trial.scenarios()]}
                actual = {p.relative_to(trial.sdd_dir).as_posix() for p in paths}
                if not expected <= actual:
                    raise ValueError('전체 시험에서 호출 시나리오 원고가 누락됐습니다: ' + ', '.join(sorted(expected - actual)))
            row = {'section': sid, 'automatic_checks': 'passed',
                   'llm_required': section.get('design_generation') == 'llm',
                   'manuscripts': [{'path': p.relative_to(out).as_posix(),
                                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
            if row['llm_required']:
                meta, _ = _split(paths[0].read_text(encoding='utf-8'))
                artifact = meta['generated_design']
                row['generated_topics'] = artifact['generated_topics']
                row['retained_topics'] = artifact['reused_topics']
                row['replayed_units'] = artifact.get('replayed_units', [])
            report['results'].append(row)

        if not stage('generate/' + sid, generate):
            report['results'].append({'section': sid, 'automatic_checks': 'failed',
                                      'error': report['stages'][-1]['error']})
            save()
    if any(row['automatic_checks'] != 'passed' for row in report['results']):
        return report
    def provenance():
        from .provenance import verify_calls
        return verify_calls(model, trial.sdd_dir, trial.build_dir / 'prompts/calls',
                            provider=trial.agent.kind, model_name=trial.agent.model,
                            runner=trial.agent.runner if trial.agent.kind == 'cli' else None,
                            allow_reused=bool(previous))
    if not stage('model-provenance', provenance):
        return report
    if not stage('audit-docs', lambda: enforce(trial, model)):
        return report
    def preview():
        korean = copy.deepcopy(trial)
        korean.raw['site'].pop('english_catalog', None)
        export_site(korean, out / 'ko-preview')
        return verify_site(out / 'ko-preview')
    if not stage('site-preflight', preview):
        return report
    if previous_catalog:
        def translation():
            from .localization_cli import prepare_catalog
            catalog = out / 'english.json'
            catalog.write_bytes((cfg.root / previous_catalog).read_bytes())
            return prepare_catalog(trial, catalog, translate=translate, replay_http=bool(previous))
        if not stage('translation', translation):
            return report
    if not stage('export-site', lambda: export_site(trial, out / 'site')):
        return report
    if not stage('verify-site', lambda: verify_site(out / 'site')):
        return report

    def repeat():
        before = (out / 'site/site-manifest.json').read_bytes()
        export_site(trial, out / 'site')
        if before != (out / 'site/site-manifest.json').read_bytes():
            raise ValueError('같은 입력의 반복 사이트 빌드가 일치하지 않습니다.')
        return {'build_id': json.loads(before)['build_id']}

    stage('repeat-site', repeat)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--translate', action='store_true')
    parser.add_argument('--continue-from', type=Path, help='Repair an interrupted or completed generation trial in a new directory')
    args = parser.parse_args()
    report = evaluate(load(args.config), args.out, translate=args.translate, previous=args.continue_from)
    success = report['stages'][-1]['stage'] == 'repeat-site' and report['stages'][-1]['status'] == 'passed'
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
