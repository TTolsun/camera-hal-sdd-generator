"""Source-extract and generate one missing public question figure, via the CLI agent."""
import argparse
import copy
import json
from pathlib import Path
import tarfile

import yaml

from sdd.config import load
from sdd.evidence import collect
from sdd.facts.model import KnowledgeModel
from sdd.generate import Generator
from sdd.llm import Agent
from sdd import impact

from inspect_history import ROOT, ARCHIVES, sha
from native_case import save, save_immutable
from prepare_public import atomic_bytes, write_exact


WORK = ROOT/'build/issue243/public-work'


def transition(path, baseline, desired, parse, raw):
    current = parse(path.read_bytes())
    if current == desired:
        return
    if current != baseline:
        raise ValueError('Prepared input conflicts with its preserved checkpoint: '+str(path))
    atomic_bytes(path, raw)


def prepare():
    archive_path = ROOT/'docs/libcamera/records/issue215/native-evidence-07.tar.xz'
    if sha(archive_path.read_bytes()) != ARCHIVES['07']:
        raise ValueError('Historical archive checksum mismatch')
    old = WORK/'prior-issue243-inputs'
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
    scope.mkdir(exist_ok=True)
    minimal = dict(sections=[dict(id='vendor-assurance', title='반환 조건',
        design_requirements=[dict(id='constraints', question=plan['question'])],
        design_topics=[dict(id='constraints', title='반환 조건', question=plan['question'],
                            covers=['constraints'], sources=[selector])])])
    scoped_config = dict(source=dict(root=str(ROOT/'build/issue243/libcamera293')), paths=dict(sections_file='sections.yaml'))
    for name, value in [('sections.yaml', minimal), ('sdd.yaml', scoped_config)]:
        path = scope/name
        if path.exists() and yaml.safe_load(path.read_bytes()) != value:
            raise ValueError('Source extraction checkpoint changed; preserve and inspect it')
        if not path.exists():
            atomic_bytes(path, yaml.safe_dump(value, allow_unicode=True).encode('utf-8'))
    cfg = load(scope/'sdd.yaml')
    model = KnowledgeModel.load(WORK/'run/facts/facts.json')
    if model.meta['source_commit'] != '293d751a814e0d4c34e85ad457ccd9d5eefd1a61':
        raise ValueError('Public restoration is not the declared immutable293 source baseline')
    fresh = KnowledgeModel(meta=dict(source_commit=model.meta['source_commit']))
    collect(cfg, fresh)
    key = 'vendor-assurance/constraints/generate-contract'
    if fresh.evidence[key]['status'] != 'available':
        raise ValueError('Exact new source window could not be extracted: '+str(fresh.evidence[key]))
    completed = (WORK/'issue243-gap-scope.json').exists()
    if completed:
        if model.evidence.get(key) != fresh.evidence[key]:
            raise ValueError('Prepared source evidence no longer matches the immutable Git window')
    old.mkdir(exist_ok=True)
    for name in ['config/sections.yaml', 'config/visuals.yaml', 'run/facts/facts.json']:
        path = old/name
        if not path.exists() and completed:
            raise ValueError('Completed preparation lost its preserved baseline: '+str(path))
        if not path.exists():
            write_exact(path, (WORK/name).read_bytes())
    baseline_sections = yaml.safe_load((old/'config/sections.yaml').read_bytes())
    sections = copy.deepcopy(baseline_sections)
    section = next(s for s in sections['sections'] if s['id'] == 'vendor-assurance')
    sources = next(t for t in section['design_topics'] if t['id'] == 'constraints')['sources']
    if any(source['id'] == selector['id'] for source in sources):
        raise ValueError('Preserved baseline already contains the new source; inspect incomplete backup')
    sources.append(selector)
    baseline_visuals = yaml.safe_load((old/'config/visuals.yaml').read_bytes())
    visuals = copy.deepcopy(baseline_visuals)
    if any(p['id'] == plan['id'] for p in visuals['sections']['vendor-assurance']):
        raise ValueError('Figure already exists; do not duplicate it')
    # The old fixed-four-node workaround introduced a success-before-null claim.
    # Keep the original graph flexibility and explicitly address the real finding.
    plan = copy.deepcopy(plan)
    plan['prompt'] += (' 생성 시도와 성공 반환을 구분하세요. null 반환으로 이어지는 공통 선행 노드는 '
                       '구성이 성공적으로 생성되었다고 단정하지 말고 생성 요청·시도를 설명하세요.')
    visuals['sections']['vendor-assurance'].append(plan)
    for name, baseline, desired in [('config/sections.yaml', baseline_sections, sections),
                                    ('config/visuals.yaml', baseline_visuals, visuals)]:
        if completed and yaml.safe_load((WORK/name).read_bytes()) != desired:
            raise ValueError('Completed preparation configuration changed; preserved: '+name)
        transition(WORK/name, baseline, desired, yaml.safe_load,
                   yaml.safe_dump(desired, allow_unicode=True, sort_keys=False).encode('utf-8'))
    baseline_facts = json.loads((old/'run/facts/facts.json').read_bytes())
    desired_facts = copy.deepcopy(baseline_facts)
    if key in desired_facts['evidence']:
        raise ValueError('Preserved facts already contain the new source; inspect incomplete backup')
    desired_facts['evidence'].update(fresh.evidence)
    if completed and json.loads((WORK/'run/facts/facts.json').read_bytes()) != desired_facts:
        raise ValueError('Completed preparation facts changed; preserved for inspection')
    transition(WORK/'run/facts/facts.json', baseline_facts, desired_facts, json.loads,
               json.dumps(desired_facts, ensure_ascii=False, indent=1).encode('utf-8'))
    for name in ['generation.yaml', 'publication.yaml', 'package.yaml', 'independent-review.yaml', 'translation-agent.yaml']:
        path = WORK/name
        value = yaml.safe_load(path.read_bytes())
        if value.setdefault('publication', {}).get('operation_id') != 'issue243-public-roles-return':
            if completed:
                raise ValueError('Completed preparation operation changed; preserved: '+name)
            value['publication']['operation_id'] = 'issue243-public-roles-return'
            atomic_bytes(path, yaml.safe_dump(value, allow_unicode=True).encode('utf-8'))
    save_immutable(WORK/'issue243-gap-scope.json', dict(source_commit=model.meta['source_commit'],
        target='vendor-assurance/constraints/configuration-contract-validity', new_evidence=key,
        literal_window=fresh.evidence[key], unchanged_evidence_count=len(baseline_facts['evidence']),
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
    prior_impact = cfg.build_dir/'impact.json'
    if prior_impact.exists():
        raw = prior_impact.read_bytes()
        write_exact(WORK/'prior-impact-reports'/('impact-'+sha(raw)+'.json'), raw)
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
