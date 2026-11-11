"""Resolve a URL fragment in the same order as HTML fragment navigation."""
from urllib.parse import unquote


def fragment_id(reference, identifiers):
    return reference if reference in identifiers else unquote(reference)
