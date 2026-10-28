"""CLI wire compatibility preserves the original local output contract."""
from __future__ import annotations

import copy
import hashlib
import json


def codex_schema(schema):
    """Remove only a keyword rejected by strict Codex output schemas.

    The original schema remains in the prompt/archive and is validated locally.
    Walk schema nodes, never arbitrary enum values or property-name mappings.
    """
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = copy.deepcopy(schema)
    result.pop('uniqueItems', None)
    for key in ('properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'):
        if isinstance(result.get(key), dict):
            result[key] = {name: codex_schema(value) for name, value in result[key].items()}
    for key in ('items', 'additionalProperties', 'contains', 'not', 'if', 'then', 'else',
                'propertyNames', 'unevaluatedProperties', 'unevaluatedItems', 'additionalItems'):
        value = result.get(key)
        if isinstance(value, dict):
            result[key] = codex_schema(value)
        elif isinstance(value, list):
            result[key] = [codex_schema(item) for item in value]
    for key in ('allOf', 'anyOf', 'oneOf', 'prefixItems'):
        if isinstance(result.get(key), list):
            result[key] = [codex_schema(value) for value in result[key]]
    return result


def schema_bytes(schema):
    return json.dumps(codex_schema(schema), ensure_ascii=False).encode('utf-8')


def schema_hash(schema):
    return hashlib.sha256(schema_bytes(schema)).hexdigest() if schema is not None else None


def validate_original(response, schema):
    if schema is None:
        return
    # Deterministic extraction does not need this optional transport at import.
    from jsonschema import Draft202012Validator, SchemaError, ValidationError
    from referencing import Registry
    from referencing.exceptions import Unresolvable
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, registry=Registry()).validate(json.loads(response))
    except (SchemaError, ValidationError, ValueError, Unresolvable) as exc:
        raise ValueError('Codex response violates its original output schema: ' + str(exc)) from exc
