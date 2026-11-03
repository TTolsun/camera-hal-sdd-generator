"""Shared publication path boundary without renderer or build dependencies."""
from pathlib import PurePosixPath


def owned_path(root, rel):
    name = PurePosixPath(rel)
    target = (root / rel).resolve()
    if name.is_absolute() or '..' in name.parts or '\\' in rel or ':' in rel or not target.is_relative_to(root.resolve()):
        raise RuntimeError(f'Unsafe site artifact path: {rel}')
    return target
