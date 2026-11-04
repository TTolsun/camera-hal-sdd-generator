"""Restore the latest merged public release; preserve its original provenance."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
import shutil
import zipfile

import yaml

from inspect_history import ROOT


def prepare():
    workspace = ROOT/'build/issue243'
    package = workspace/'public-sdd/publication/submission-diagnosis'
    out = workspace/'public-work'
    if out.exists():
        raise ValueError('Public work root already exists; inspect and resume it')
    out.mkdir()
    for directory in ['config', 'templates', 'current-style', 'historical-style', 'reader-preserved-style']:
        shutil.copytree(package/directory, out/directory)
    shutil.copytree(package/'manuscripts', out/'run/manuscripts')
    (out/'run/facts').mkdir(parents=True)
    (out/'run/facts/facts.json').write_bytes(gzip.decompress((package/'facts293.json.gz').read_bytes()))
    shutil.copyfile(package/'english.json', out/'run/english.json')
    shutil.copyfile(package/'site-intro.md', out/'site-intro.md')
    with zipfile.ZipFile(package/'cli-evidence.zip') as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            target = (out/entry.filename).resolve()
            if not target.is_relative_to(out.resolve()):
                raise ValueError('Archive path leaves the isolated work root')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    for path in package.glob('*.json'):
        shutil.copyfile(path, out/path.name)
    shutil.copyfile(package/'consistency-review.json', out/'build/consistency-review.json')
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
        (out/profile.name).write_text(yaml.safe_dump(value, allow_unicode=True), encoding='utf-8')
    report = dict(mode='restored-original-public-inputs', public_base='61184f28d82903512b0138f9511e2e3f6f251098',
        source_commit='293d751a814e0d4c34e85ad457ccd9d5eefd1a61',
        note='Path relocation changes build identity. No fresh build, extraction, generation or review is claimed.',
        original_manuscripts={p.relative_to(package/'manuscripts').as_posix(): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                              for p in (package/'manuscripts').rglob('*.md')}, human_review='pending')
    (out/'restoration.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    prepare()
