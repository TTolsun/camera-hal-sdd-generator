"""Source-extract and generate one missing public question figure, via the CLI agent."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tarfile

import yaml

from sdd.config import load
from sdd.evidence import collect
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator
from sdd.llm import Agent
from sdd import impact

from inspect_history import ROOT, ARCHIVES, sha
from native_case import save


WORK = ROOT/'build/issue243/public-work'


def prepare():
    archive_path = ROOT/'docs/libcamera/records/issue215/native-evidence-07.tar.xz'
    if sha(archive_path.read_bytes()) != ARCHIVES['07']:
        raise ValueError('Historical archive checksum mismatch')
    old = WORK/'prior-issue243-inputs'
    if old.exists():
        raise ValueError('Gap preparation already started; preserve and resume existing inputs')
    with tarfile.open(archive_path) as archive:
        prefix = 'build/issue215/refinement-runs-15/vendor-assurance/step-01/config/'
        original_section = next(s for s in yaml.safe_load(archive.extractfile(prefix+'sections.yaml'))['sections']
                                if s['id'] == 'vendor-assurance')
        selector = next(s for t in original_section['design_topics'] if t['id'] == 'constraints'
                        for s in t['sources'] if s['id'] == 'generate-contract')
        plan = next(p for p in yaml.safe_load(archive.extractfile(prefix+'visuals.yaml'))['sections']['vendor-assurance']
                    if p['id'] == 'configuration-contract-validity')
    # Re-extract this exact window from the real immutable public Git checkout.
    # Existing structural facts/runtime and other original evidence stay at293.
    scope = WORK/'gap-source'
    scope.mkdir()
    minimal = dict(sections=[dict(id='vendor-assurance', title='반환 조건',
        design_requirements=[dict(id='constraints', question=plan['question'])],
        design_topics=[dict(id='constraints', title='반환 조건', question=plan['question'],
                            covers=['constraints'], sources=[selector])])])
    (scope/'sections.yaml').write_text(yaml.safe_dump(minimal, allow_unicode=True), encoding='utf-8')
    (scope/'sdd.yaml').write_text(yaml.safe_dump(dict(source=dict(root=str(ROOT/'build/issue243/libcamera293')),
        paths=dict(sections_file='sections.yaml'))), encoding='utf-8')
    cfg = load(scope/'sdd.yaml')
    model = KnowledgeModel.load(WORK/'run/facts/facts.json')
    fresh = KnowledgeModel(meta=dict(source_commit=model.meta['source_commit']))
    collect(cfg, fresh)
    key = 'vendor-assurance/constraints/generate-contract'
    if fresh.evidence[key]['status'] != 'available':
        raise ValueError('Exact new source window could not be extracted: '+str(fresh.evidence[key]))
    if key in model.evidence:
        raise ValueError('New evidence ID already exists; inspect previous preparation')
    old.mkdir()
    for name in ['config/sections.yaml', 'config/visuals.yaml', 'run/facts/facts.json']:
        path = old/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WORK/name, path)
    sections = yaml.safe_load((WORK/'config/sections.yaml').read_bytes())
    section = next(s for s in sections['sections'] if s['id'] == 'vendor-assurance')
    next(t for t in section['design_topics'] if t['id'] == 'constraints')['sources'].append(selector)
    visuals = yaml.safe_load((WORK/'config/visuals.yaml').read_bytes())
    if any(p['id'] == plan['id'] for p in visuals['sections']['vendor-assurance']):
        raise ValueError('Figure already exists; do not duplicate it')
    # The old fixed-four-node workaround introduced a success-before-null claim.
    # Keep the original graph flexibility and explicitly address the real finding.
    plan = copy.deepcopy(plan)
    plan['prompt'] += (' 생성 시도와 성공 반환을 구분하세요. null 반환으로 이어지는 공통 선행 노드는 '
                       '구성이 성공적으로 생성되었다고 단정하지 말고 생성 요청·시도를 설명하세요.')
    visuals['sections']['vendor-assurance'].append(plan)
    (WORK/'config/sections.yaml').write_text(yaml.safe_dump(sections, allow_unicode=True, sort_keys=False), encoding='utf-8')
    (WORK/'config/visuals.yaml').write_text(yaml.safe_dump(visuals, allow_unicode=True, sort_keys=False), encoding='utf-8')
    model.evidence.update(fresh.evidence)
    model.save(WORK/'run/facts/facts.json')
    for name in ['generation.yaml', 'publication.yaml', 'package.yaml', 'independent-review.yaml', 'translation-agent.yaml']:
        path = WORK/name
        value = yaml.safe_load(path.read_bytes())
        value.setdefault('publication', {})['operation_id'] = 'issue243-public-roles-return'
        path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding='utf-8')
    save(WORK/'issue243-gap-scope.json', dict(source_commit=model.meta['source_commit'],
        target='vendor-assurance/constraints/configuration-contract-validity', new_evidence=key,
        literal_window=fresh.evidence[key], unchanged_evidence_count=len(model.evidence)-1,
        extraction='One literal window from Git293; no new structural extraction or runtime trial',
        human_review='pending'))


def generate():
    cfg = load(WORK/'generation.yaml')
    model = KnowledgeModel.load(cfg.facts_path)
    previous = KnowledgeModel.load(WORK/'prior-issue243-inputs/run/facts/facts.json')
    commit = model.meta['source_commit']
    report = impact.compute(cfg, model, [], commit, commit, previous)
    for sid, reasons in impact.config_changes(cfg, model).items():
        report.sections.setdefault(sid, []).extend(reasons)
    report.save(cfg.build_dir/'impact.json')
    save(WORK/'issue243-effective-generation.json', dict(kind=cfg.agent.kind, runner=cfg.agent.runner,
        model=cfg.agent.model, command=cfg.agent.command, args=cfg.agent.args,
        selected_sections=['vendor-assurance'], other_config_changes={sid: why for sid, why in report.sections.items()
                                                                  if sid != 'vendor-assurance'}))
    if 'vendor-assurance' not in report.sections:
        raise ValueError('No computed impact for the prepared question; do not force regeneration')
    # The common Generator/Agent path executes the explicitly selected native
    # CLI. No model API, imported response or manual manuscript is substituted.
    written = Generator(cfg, model, Agent(cfg.agent, dump_dir=cfg.build_dir/'prompts')).run(
        section_ids=['vendor-assurance'], impact=report)
    print([str(p) for p in written])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'generate'])
    args = parser.parse_args()
    prepare() if args.mode == 'prepare' else generate()
