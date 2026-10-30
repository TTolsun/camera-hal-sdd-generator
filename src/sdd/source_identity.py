"""Stable identity of a rendered immutable source excerpt."""
import hashlib


def anchor(record):
    key = f"{record['file']}:{record['line']}:{record['sha256']}"
    return 'source-' + hashlib.sha256(key.encode()).hexdigest()[:16]
