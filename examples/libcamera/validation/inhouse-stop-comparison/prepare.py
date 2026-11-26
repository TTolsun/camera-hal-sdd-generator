"""Create two isolated first-run configurations from the in-house template."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
GENERATOR = HERE.parents[3]
TEMPLATE = GENERATOR / 'examples/inhouse-template'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--compdb', type=Path, help='Optional DB path for doctor or extraction. The trial reads existing facts.')
    parser.add_argument('--facts-dir', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    facts_dir = args.facts_dir.resolve()
    compdb = args.compdb.resolve() if args.compdb else source / 'build/compile_commands.json'

    commit = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=source, text=True,
    ).strip()
    with (facts_dir / 'facts.json').open(encoding='utf-8') as stream:
        facts_commit = json.load(stream)['meta']['source_commit']
    if commit != args.commit or facts_commit != commit:
        parser.error(f'Expected {args.commit}, but source has {commit} and facts have {facts_commit}.')

    cfg = yaml.safe_load((TEMPLATE / 'sdd.yaml').read_bytes())
    cfg['source'].update(root=str(source), compile_commands=str(compdb), ndk_build={'enabled': False})
    cfg['output'] = {'facts_dir': str(facts_dir)}
    cfg['paths'].update(
        prompts=str(GENERATOR / 'prompts'),
        templates=str(GENERATOR / 'templates'),
        style=str(GENERATOR / 'style'),
        clang_uml_file=str(GENERATOR / 'config/clang-uml.yaml'),
        scenarios_file=str(TEMPLATE / 'config/scenarios.yaml'),
    )
    cfg['site'].update(source_url='https://github.com/TTolsun/libcamera-sdd', source_link='github')
    cfg['visuals']['file'] = str(HERE / 'visuals.yaml')

    root = args.out.resolve()
    root.mkdir(parents=True)
    for condition in ('first-run', 'focused'):
        project = root / condition
        project.mkdir()
        trial = copy.deepcopy(cfg)
        trial['paths']['sections_file'] = str(HERE / f'{condition}.yaml')
        (project / 'sdd.yaml').write_text(yaml.safe_dump(trial, allow_unicode=True), encoding='utf-8')


if __name__ == '__main__':
    main()
