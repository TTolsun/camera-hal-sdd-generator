"""Restore the latest merged public release; preserve its original provenance."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

import yaml

from inspect_history import ROOT


def atomic_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name+'.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_exact(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Restoration checkpoint conflicts with original input; preserved: '+str(path))
        return
    atomic_bytes(path, raw)


def prepare():
    workspace = ROOT/'build/issue243'
    package = workspace/'public-sdd/publication/submission-diagnosis'
    out = workspace/'public-work'
    if (out/'restoration.json').exists():
        report = json.loads((out/'restoration.json').read_bytes())
        originals = {p.relative_to(package/'manuscripts').as_posix(): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                     for p in (package/'manuscripts').rglob('*.md')}
        legacy_originals = {name: digest for name, digest in originals.items() if '/' not in name}
        if (report.get('mode') != 'restored-original-public-inputs'
                or report.get('source_commit') != '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
                or not originals or report.get('original_manuscripts') not in (originals, legacy_originals)):
            raise ValueError('Invalid restoration checkpoint; preserve and inspect it')
        required = [out/'run/manuscripts'/name for name in originals]
        required += [out/'run/facts/facts.json', out/'run/english.json', out/'site-intro.md',
                     out/'build/consistency-review.json']
        required += [out/p.name for p in (package/'profiles').glob('*.yaml')]
        required += [out/d/p.relative_to(package/d) for d in ['config', 'templates', 'current-style',
                     'historical-style', 'reader-preserved-style'] for p in (package/d).rglob('*') if p.is_file()]
        if any(not p.is_file() for p in required):
            raise ValueError('Restoration checkpoint has missing inputs; preserve and inspect it')
        # Later stages may change manuscripts, facts, English, the five active
        # profiles, section/visual plans and consistency reports. These fixed
        # publication inputs have no such transition in this experiment.
        fixed = [(out/'site-intro.md', package/'site-intro.md')]
        fixed += [(out/d/p.relative_to(package/d), p) for d in ['config', 'templates', 'current-style',
                  'historical-style', 'reader-preserved-style'] for p in (package/d).rglob('*')
                  if p.is_file() and p.name not in ('sections.yaml', 'visuals.yaml')]
        if any(target.read_bytes() != original.read_bytes() for target, original in fixed):
            raise ValueError('Fixed restoration input changed; preserved for inspection')
        print('Original restoration metadata and fixed inputs verified; later transitions retain their own checks.')
        return
    out.mkdir(exist_ok=True)
    protected = set()
    for directory in ['config', 'templates', 'current-style', 'historical-style', 'reader-preserved-style']:
        for path in (package/directory).rglob('*'):
            if path.is_file():
                relative = Path(directory)/path.relative_to(package/directory)
                protected.add(relative.as_posix())
                write_exact(out/relative, path.read_bytes())
    for path in (package/'manuscripts').rglob('*'):
        if path.is_file():
            relative = Path('run/manuscripts')/path.relative_to(package/'manuscripts')
            protected.add(relative.as_posix())
            write_exact(out/relative, path.read_bytes())
    for relative, raw in [('run/facts/facts.json', gzip.decompress((package/'facts293.json.gz').read_bytes())),
                          ('run/english.json', (package/'english.json').read_bytes()),
                          ('site-intro.md', (package/'site-intro.md').read_bytes())]:
        protected.add(relative)
        write_exact(out/relative, raw)
    with zipfile.ZipFile(package/'cli-evidence.zip') as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            target = (out/entry.filename).resolve()
            if not target.is_relative_to(out.resolve()):
                raise ValueError('Archive path leaves the isolated work root')
            if target.relative_to(out.resolve()).as_posix() in protected:
                raise ValueError('Archive collides with a restored package file: '+entry.filename)
            write_exact(target, archive.read(entry))
    for path in package.glob('*.json'):
        write_exact(out/path.name, path.read_bytes())
    write_exact(out/'build/consistency-review.json', (package/'consistency-review.json').read_bytes())
    # These are path relocations only, not a new model or a rewritten receipt.
    old = 'C:/Users/baboe/.codex/worktrees/7b3d/camera-hal-sdd-generator'
    mappings = [(old+'/build/libcamera-content/draft', out),
                (old+'/build/libcamera-content/public', workspace/'public-sdd'),
                (old+'/build/libcamera-content/source', workspace/'libcamera293'),
                (old, ROOT)]
    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str):
            path = value.replace('\\', '/')
            for prefix, target in mappings:
                if path == prefix or path.startswith(prefix+'/'):
                    return str(target/path[len(prefix):].lstrip('/'))
        return value
    for profile in (package/'profiles').glob('*.yaml'):
        value = relocate(yaml.safe_load(profile.read_bytes()))
        write_exact(out/profile.name, yaml.safe_dump(value, allow_unicode=True).encode('utf-8'))
    public_base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=workspace/'public-sdd', text=True).strip()
    report = dict(mode='restored-original-public-inputs', public_base=public_base,
        source_commit='293d751a814e0d4c34e85ad457ccd9d5eefd1a61',
        note='Path relocation changes build identity. No fresh build, extraction, generation or review is claimed.',
        original_manuscripts={p.relative_to(package/'manuscripts').as_posix(): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                              for p in (package/'manuscripts').rglob('*.md')}, human_review='pending')
    for name, digest in report['original_manuscripts'].items():
        if __import__('hashlib').sha256((out/'run/manuscripts'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Restored manuscript differs from original public package: '+name)
    write_exact(out/'restoration.json', (json.dumps(report, indent=2)+'\n').encode('utf-8'))
    print(out)


if __name__ == '__main__':
    prepare()
