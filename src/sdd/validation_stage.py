"""Stage-scoped input bytes and pure computations, never a verdict cache."""
from contextlib import contextmanager
from contextlib import nullcontext
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import yaml

_current = ContextVar('sdd_validation_stage', default=None)


class InputChanged(ValueError):
    pass


class Inputs:
    def __init__(self):
        self.files, self.values, self.parses = {}, {}, {}
        self.objects, self.directories = {}, {}
        self.rollbacks = []
        self.stamps, self.aliases = {}, {}

    @staticmethod
    def stamp(path):
        if not path.exists():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ino, stat.st_mode

    def pin(self, cfg, model=None):
        for value in (cfg, model):
            if value is not None and id(value) not in self.objects:
                self.objects[id(value)] = (value, deepcopy(asdict(value)))
        if model is not None and hasattr(model, '_loaded_input'):
            path, raw = model._loaded_input
            if self.read(path) != raw:
                raise InputChanged(f'Facts changed since load: {path}; reload facts')
        if model is not None and cfg.source_root.exists():
            from .trial_workspace import contained_path
            for record in model.evidence.values():
                if record.get('file') and not record['file'].startswith('@') and record.get('kind') != 'product':
                    self.read(contained_path(cfg.source_root, record['file']), optional=True)
        git = cfg.source_root/'.git'
        if git.exists():
            if git.is_file():
                pointer = self.read(git).decode('utf-8').strip()
                if not pointer.startswith('gitdir: '):
                    raise InputChanged('Invalid source worktree pointer')
                git = (cfg.source_root/pointer[8:]).resolve()
            head = self.read(git/'HEAD', optional=True)
            self.read(git/'packed-refs', optional=True)
            if head and head.startswith(b'ref: '):
                common = self.read(git/'commondir', optional=True)
                refs = (git/common.decode('utf-8').strip()).resolve() if common else git
                self.read(refs/'packed-refs', optional=True)
                self.read(refs/head.decode('utf-8')[5:].strip(), optional=True)
        for path, raw in getattr(cfg, '_loaded_inputs', {}).items():
            if self.read(path, optional=True) != raw:
                raise InputChanged(f'Configuration changed since load: {path}; reload configuration')
        for path in (cfg.sections_file, cfg.scenarios_file, cfg.facts_path,
                     *cfg.paths.values()):
            if Path(path).is_file():
                self.read(path)
        for directory, pattern in ((cfg.style_dir, '*.md'), (cfg.templates_dir, '*'),
                                   (Path(__file__).parent, '*.py')):
            key = (directory, pattern)
            if key not in self.directories:
                paths = tuple(sorted(p for p in directory.rglob(pattern) if p.is_file()))
                self.directories[key] = paths
                for path in paths:
                    self.read(path)

    def read(self, path, *, optional=False):
        alias = Path(path).absolute()
        path = alias.resolve()
        self.aliases[alias] = path
        if path not in self.files:
            before = self.stamp(path)
            self.files[path] = path.read_bytes() if path.exists() else None
            self.stamps[path] = self.stamp(path)
            if self.stamps[path] != before:
                raise InputChanged(f'Input changed while reading: {path}')
        raw = self.files[path]
        if raw is None and not optional:
            raise FileNotFoundError(path)
        return raw

    def memo(self, key, make):
        if key not in self.values:
            self.values[key] = make()
        return deepcopy(self.values[key])

    def parse(self, kind, raw, parser):
        key = ('parse', kind, raw)
        if key not in self.values:
            self.parses[kind] = self.parses.get(kind, 0) + 1
        return self.memo(key, lambda: parser(raw))

    def verify(self):
        for alias, path in self.aliases.items():
            if alias.resolve() != path:
                raise InputChanged(f'Input path changed during validation: {alias}')
        for value, original in self.objects.values():
            if asdict(value) != original:
                raise InputChanged('In-memory validation input changed; previous output preserved')
        for (directory, pattern), original in self.directories.items():
            if tuple(sorted(p for p in directory.rglob(pattern) if p.is_file())) != original:
                raise InputChanged(f'Validation input set changed: {directory}; previous output preserved')
        for path, raw in self.files.items():
            current = path.read_bytes() if path.exists() else None
            if current != raw or self.stamp(path) != self.stamps[path]:
                raise InputChanged(f'Input changed during validation: {path}; previous output preserved')

    def manifest(self):
        return {str(path): hashlib.sha256(raw).hexdigest() if raw is not None else None
                for path, raw in self.files.items()}

    def produced(self, path, expected):
        """A known atomic checkpoint update is an output, not an external edit."""
        path = Path(path).resolve()
        if path.read_bytes() != expected:
            raise InputChanged(f'Generated checkpoint changed during save: {path}')
        if path in self.files:
            self.files[path] = expected
            self.stamps[path] = self.stamp(path)


def current():
    return _current.get()


def read_bytes(path, *, optional=False):
    inputs = current()
    if inputs is not None:
        return inputs.read(path, optional=optional)
    return Path(path).read_bytes() if not optional or Path(path).exists() else None


def read_text(path):
    return read_bytes(path).decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')


def parse_yaml(raw):
    inputs = current()
    return inputs.parse('yaml', raw, yaml.safe_load) if inputs else yaml.safe_load(raw)


def load_yaml(path, *, optional=False):
    raw = read_bytes(path, optional=optional)
    text = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n') if raw is not None else None
    return (parse_yaml(text) if text is not None else None) or {}


def load_json(path):
    raw = read_bytes(path)
    inputs = current()
    def decode(data):
        return json.loads(data.decode('utf-8'))
    return inputs.parse('json', raw, decode) if inputs else decode(raw)


@contextmanager
def stage():
    if current() is not None:
        yield current()
        return
    inputs = Inputs()
    token = _current.set(inputs)
    try:
        yield inputs
        inputs.verify()
    except BaseException:
        for rollback in reversed(inputs.rollbacks):
            rollback()
        raise
    finally:
        _current.reset(token)


def staged(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with stage() as inputs:
            configured = args and hasattr(args[0], 'sections_file')
            if configured:
                model = args[1] if len(args) > 1 and hasattr(args[1], 'evidence') else None
                inputs.pin(args[0], model)
            from .generation_run import observe
            with observe(args[0], function.__name__) if configured and function.__name__ != 'audit' else nullcontext():
                return function(*args, **kwargs)
    return wrapped


def verify():
    if current() is not None:
        current().verify()
