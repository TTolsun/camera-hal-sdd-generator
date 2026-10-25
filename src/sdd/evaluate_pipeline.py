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
from dataclasses import asdict
import yaml

from .config import load, section_output
from .document_health import enforce, page_path
from .evidence import collect
from .export_site import export_site
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent
from .site_build import verify_site


def evaluate(cfg, out: Path, *, translate: bool = False, previous: Path | None = None):
    if cfg.agent.kind not in ('ollama', 'openai-compatible'):
        raise ValueError('전체 생성 시험에는 실제 ollama 또는 openai-compatible 연결이 필요합니다.')
    out = out.resolve()
    protected = [cfg.root, cfg.source_root, cfg.sdd_dir, cfg.facts_dir]
    if (out.exists() or any(p.resolve().is_relative_to(out) for p in protected)
            or any(out.is_relative_to(p.resolve()) for p in protected[1:])):
        raise ValueError('시험 출력에는 기존 입력·원고를 포함하지 않는 새 디렉터리가 필요합니다.')
    if previous:
        previous = previous.resolve()
        if previous.is_symlink() or out.is_relative_to(previous) or previous.is_relative_to(out):
            raise ValueError('재개 시험은 이전 시험과 분리된 새 디렉터리가 필요합니다.')
    out.mkdir(parents=True)
    trial = copy.deepcopy(cfg)
    trial.paths.update(sections_file=cfg.sections_file, scenarios_file=cfg.scenarios_file,
                       prompts=cfg.prompts_dir, templates=cfg.templates_dir, style=cfg.style_dir)
    trial.paths['glossary_file'] = cfg.paths.get('glossary_file', cfg.root / 'config/glossary.yaml')
    trial.root = out
    trial.sdd_dir = out / 'manuscripts'
    trial.diagrams_dir = trial.sdd_dir / 'diagrams'
    trial.facts_dir = out / 'facts'
    site = trial.raw.setdefault('site', {})
    site['enabled'] = False
    for key in ('intro', 'mermaid_dir'):
        if site.get(key):
            site[key] = str((cfg.root / site[key]).resolve())
    visuals = trial.raw.get('visuals', {})
    if visuals.get('file'):
        visuals['file'] = str((cfg.root / visuals['file']).resolve())
    previous_catalog = cfg.raw.get('site', {}).get('english_catalog')
    if previous_catalog:
        site['english_catalog'] = str(out / 'english.json')
    snapshot = copy.deepcopy(trial.raw)
    snapshot['source'] = {**snapshot.get('source', {}), 'root': str(trial.source_root),
                          'compile_commands': str(trial.compile_commands)}
    snapshot['output'] = {'facts_dir': str(trial.facts_dir), 'sdd_dir': str(trial.sdd_dir),
                          'diagrams_dir': str(trial.diagrams_dir)}
    snapshot['paths'] = {key: str(value) for key, value in trial.paths.items()}
    snapshot['agent'] = asdict(trial.agent)
    (out / 'sdd.yaml').write_text(yaml.safe_dump(snapshot, allow_unicode=True), encoding='utf-8')
    report = {
        'schema': 1, 'source_commit': None, 'provider': cfg.agent.kind, 'model': cfg.agent.model,
        'sections_sha256': hashlib.sha256(cfg.sections_file.read_bytes()).hexdigest(),
        'engine_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(Path(__file__).parent.glob('*.py'))},
        'settings': {key: getattr(cfg.agent, key) for key in
                     ('max_input_chars', 'num_ctx', 'max_output_tokens', 'temperature', 'think')},
        'results': [], 'stages': [], 'semantic_review': 'pending',
        'human_approval': 'pending', 'publishable': False,
        'mode': 'repair' if previous else 'fresh',
    }

    def save():
        temp = out / 'evaluation.tmp'
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(out / 'evaluation.json')

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
            from .export_html import _split
            old_bytes = (previous / 'evaluation.json').read_bytes()
            old = json.loads(old_bytes)
            expected = {s['id'] for s in trial.sections()}
            if (old.get('schema') != 1 or old.get('source_commit') != model.meta['source_commit']
                    or old.get('provider') != trial.agent.kind or old.get('model') != trial.agent.model
                    or {row['section'] for row in old.get('results', [])} != expected):
                raise ValueError('같은 소스·모델의 모든 섹션 결과가 기록된 이전 시험만 재개할 수 있습니다.')
            for row in old['results']:
                if row['automatic_checks'] != 'passed':
                    continue
                for item in row['manuscripts']:
                    source = (previous / item['path']).resolve()
                    if (not source.is_relative_to((previous / 'manuscripts').resolve())
                            or hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']):
                        raise ValueError('이전 시험 원고가 기록된 해시와 다릅니다.')
                    meta, _ = _split(source.read_text(encoding='utf-8'))
                    if meta.get('generated_design') and any(
                            value != f'{trial.agent.kind}/{trial.agent.model}'
                            for value in meta['generated_design'].get('topic_agents', {}).values()):
                        raise ValueError('이전 원고의 모델 작성자가 시험 설정과 다릅니다.')
            from .provenance import verify_calls
            prior_authorship = verify_calls(model, previous / 'manuscripts', previous / 'build/prompts/calls',
                                             provider=trial.agent.kind, model_name=trial.agent.model,
                                             allow_reused=True)
            for name, destination in [('manuscripts', trial.sdd_dir),
                                      ('build/prompts/calls', trial.build_dir / 'prompts/calls')]:
                source = previous / name
                if source.exists():
                    if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):
                        raise ValueError('재개 입력에는 심볼릭 링크를 사용할 수 없습니다.')
                    shutil.copytree(source, destination, dirs_exist_ok=True)
            report['continued_from_sha256'] = hashlib.sha256(old_bytes).hexdigest()
            return {'previous_results': len(old['results']), 'source_commit': old['source_commit'],
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
                impact = ImpactReport(base=model.meta['source_commit'], head=model.meta['source_commit'], sections=[sid])
            paths = Generator(trial, model, agent).run([sid], **({'impact': impact} if impact else {}))
            row = {'section': sid, 'automatic_checks': 'passed',
                   'llm_required': section.get('design_generation') == 'llm',
                   'manuscripts': [{'path': p.relative_to(out).as_posix(),
                                    'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
            if row['llm_required']:
                from .export_html import _split
                meta, _ = _split(paths[0].read_text(encoding='utf-8'))
                artifact = meta['generated_design']
                row['generated_topics'] = artifact['generated_topics']
                row['retained_topics'] = artifact['reused_topics']
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
                            provider=trial.agent.kind, model_name=trial.agent.model, allow_reused=bool(previous))
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
            return prepare_catalog(trial, catalog, translate=translate)
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
    parser.add_argument('--continue-from', type=Path, help='Repair a completed generation trial in a new directory')
    args = parser.parse_args()
    report = evaluate(load(args.config), args.out, translate=args.translate, previous=args.continue_from)
    success = report['stages'][-1]['stage'] == 'repeat-site' and report['stages'][-1]['status'] == 'passed'
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
