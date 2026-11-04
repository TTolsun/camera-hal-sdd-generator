"""Shared publication prerequisite and output report verification."""
import hashlib
from .validation_stage import read_bytes, load_json


def check_reports(cfg, gate, *, reports=None):
    """Require declared reports at their producing boundary, before copying."""
    checked = []
    for row in cfg.publication.get('reports', []) if reports is None else reports:
        if not all(row.get(key) for key in ('path', 'gate', 'producer', 'sha256', 'bindings')):
            raise ValueError('Publication reports need path/gate/producer/sha256/bindings')
        if row['gate'] != gate:
            continue
        path = cfg.root/row['path']
        raw = read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Publication report hash mismatch: ' + row['path'])
        data = load_json(path)
        if any(data.get(key) != value for key, value in row['bindings'].items()):
            raise ValueError('Publication report stage/input/status mismatch: ' + row['path'])
        checked.append(dict(**row, verified=True))
    return checked

