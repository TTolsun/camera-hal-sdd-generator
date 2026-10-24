"""Windows update.extract_cmd adapter for a dedicated libcamera WSL build.

The Linux side rebuilds and extracts the exact requested commit. It never calls
an LLM or reads cached facts. Internal projects should supply their own adapter.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def wsl_path(value: str | Path) -> str:
    path = Path(value).resolve()
    if not path.drive or len(path.drive) != 2:
        raise ValueError('Use a local Windows drive path for the WSL exchange files.')
    return '/mnt/' + path.drive[0].lower() + '/' + path.as_posix()[3:]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, help='Linux extraction config stored on a Windows drive')
    p.add_argument('--build-dir', required=True, help='Dedicated Meson build directory in WSL')
    p.add_argument('--python', required=True, help='Linux Python with generator dependencies installed')
    p.add_argument('--distro', default='Ubuntu')
    p.add_argument('--linux', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--commit', help=argparse.SUPPRESS)
    p.add_argument('--out', help=argparse.SUPPRESS)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not args.linux:
        # No shell interpolation and no wider Ollama network binding are needed.
        command = ['wsl', '-d', args.distro, '--', args.python, wsl_path(__file__),
                   '--linux', '--config', wsl_path(args.config), '--build-dir', args.build_dir,
                   '--python', args.python, '--commit', os.environ['SDD_SOURCE_COMMIT'],
                   '--out', wsl_path(os.environ['SDD_FACTS_OUTPUT'])]
        subprocess.run(command, check=True)
        return
    sys.path.insert(0, str(root / 'src'))
    from sdd import compdb, extract, source_git
    from sdd.config import load
    cfg = load(Path(args.config))
    if not source_git.is_clean(cfg.source_root):
        raise RuntimeError('The dedicated WSL source checkout must be clean.')
    original = source_git.current_ref(cfg.source_root)
    try:
        source_git.checkout(cfg.source_root, args.commit)
        subprocess.run(['ninja', '-C', args.build_dir], check=True)
        entries = compdb.load_entries(Path(args.build_dir) / 'compile_commands.json')
        normalized = compdb.normalize(entries, compdb.clang_resource_dir('clang'))
        cfg.compile_commands.parent.mkdir(parents=True, exist_ok=True)
        cfg.compile_commands.write_text(json.dumps(normalized, ensure_ascii=False), encoding='utf-8')
        output = Path(args.out)
        if output.name != 'facts.json':
            raise ValueError('Expected the staged facts.json destination.')
        cfg.facts_dir = output.parent
        extract.run(cfg)
    finally:
        source_git.checkout_ref(cfg.source_root, original)


if __name__ == '__main__':
    main()
