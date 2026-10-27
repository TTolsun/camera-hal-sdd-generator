"""Path checks and configuration copies for isolated trials, without trial policy."""
from __future__ import annotations

import copy
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import yaml

from .config import Config


def is_link(path: Path) -> bool:
    """Reject Windows reparse points too, including on Python 3.11."""
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def reject_symlinks(path: Path, *, recursive: bool = False) -> Path:
    """Check the original path before resolve can hide a linked component."""
    path = Path(path).absolute()
    def check(candidate):
        if is_link(candidate):
            raise ValueError(f'Trial inputs and outputs cannot use symbolic links: {candidate}')
    for candidate in [path, *path.parents]:
        check(candidate)
    if recursive and path.is_dir():
        for candidate in path.rglob('*'):
            check(candidate)
    return path


def contained_path(root: Path, relative: str | Path) -> Path:
    """Find an unlinked file below a root; reject traversal before reading it."""
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or '..' in relative.parts:
        raise ValueError(f'Expected a relative path within the trial: {relative}')
    root = reject_symlinks(root).resolve()
    candidate = reject_symlinks(root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f'Path escapes the trial: {relative}')
    return candidate


def validate_output(cfg: Config, out: Path, *, previous: Iterable[Path] = ()) -> Path:
    """Allow a new build trial under cfg.root, isolated from its actual inputs."""
    out = reject_symlinks(out).resolve()
    protected = [cfg.source_root, cfg.compile_commands, cfg.sdd_dir, cfg.facts_dir,
                 cfg.diagrams_dir, cfg.sections_file, cfg.scenarios_file, cfg.clang_uml_file,
                 cfg.paths.get('glossary_file', cfg.config_dir / 'glossary.yaml'), cfg.prompts_dir,
                 cfg.templates_dir, cfg.style_dir,
                 *[value for key, value in cfg.paths.items() if key != 'config']]
    site = cfg.raw.get('site') or {}
    visuals = cfg.raw.get('visuals') or {}
    protected += [(cfg.root / path).resolve() for path in
                  [site.get('intro'), site.get('english_catalog'), site.get('mermaid_dir'), visuals.get('file')]
                  if path]
    protected += [reject_symlinks(path).resolve() for path in previous]
    if (out.exists() or cfg.root.resolve().is_relative_to(out)
            or any(path.resolve().is_relative_to(out) or out.is_relative_to(path.resolve())
                   for path in protected)):
        raise ValueError('The trial needs a new output directory isolated from inputs and manuscripts.')
    return out


def clone_config(cfg: Config, out: Path, *, sections_file: Path | None = None) -> Config:
    """Redirect outputs while preserving the input assets resolved by cfg."""
    trial = copy.deepcopy(cfg)
    trial.paths.update(config=cfg.config_dir, sections_file=sections_file or cfg.sections_file,
                       scenarios_file=cfg.scenarios_file, clang_uml_file=cfg.clang_uml_file,
                       prompts=cfg.prompts_dir, templates=cfg.templates_dir, style=cfg.style_dir,
                       glossary_file=cfg.paths.get('glossary_file', cfg.config_dir / 'glossary.yaml'))
    trial.paths = {key: Path(value).resolve() for key, value in trial.paths.items()}
    trial.root = Path(out).resolve()
    trial.sdd_dir = trial.root / 'manuscripts'
    trial.diagrams_dir = trial.sdd_dir / 'diagrams'
    trial.facts_dir = trial.root / 'facts'
    site = trial.raw.get('site') or {}
    trial.raw['site'] = site
    site['enabled'] = False
    for key in ('intro', 'mermaid_dir', 'english_catalog'):
        if site.get(key):
            site[key] = str((cfg.root / site[key]).resolve())
    visuals = trial.raw.get('visuals') or {}
    if visuals.get('file'):
        visuals['file'] = str((cfg.root / visuals['file']).resolve())
    return trial


def write_snapshot(trial: Config, path: Path) -> Path:
    """Serialize the effective Config, including explicit CLI model and runner."""
    path = Path(path)
    if path.parent.resolve() != trial.root.resolve():
        raise ValueError('The configuration snapshot must be in the trial root.')
    snapshot = copy.deepcopy(trial.raw)
    snapshot['source'] = {**(snapshot.get('source') or {}), 'root': str(trial.source_root),
                          'compile_commands': str(trial.compile_commands),
                          'exclude': list(trial.exclude), 'ndk_build': copy.deepcopy(trial.ndk_build)}
    snapshot['output'] = {'facts_dir': str(trial.facts_dir), 'sdd_dir': str(trial.sdd_dir),
                          'diagrams_dir': str(trial.diagrams_dir)}
    snapshot['paths'] = {key: str(value) for key, value in trial.paths.items()}
    snapshot['agent'] = asdict(trial.agent)
    snapshot['tools'] = {**(snapshot.get('tools') or {}), 'clang_uml': trial.clang_uml_bin}
    snapshot['review'] = {**(snapshot.get('review') or {}), 'require_citations': trial.require_citations,
                          'max_retries': trial.max_retries}
    snapshot['facts'] = {**(snapshot.get('facts') or {}), 'package_depth': trial.package_depth}
    path.write_text(yaml.safe_dump(snapshot, allow_unicode=True), encoding='utf-8', newline='\n')
    return path
