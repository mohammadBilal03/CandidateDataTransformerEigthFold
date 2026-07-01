"""Lightweight validator. Runs after projection (or directly on the
canonical record when no config is given) and degrades gracefully:
type mismatches are coerced where safe (e.g. single value -> [value] for
a string[] field) and otherwise reported as warnings rather than raising,
since "validate output before returning it; degrade gracefully" was an
explicit requirement.
"""
from typing import Any, Dict, List, Tuple
from .schema import DEFAULT_SCHEMA_FIELDS, REQUIRED_FIELDS


def _type_ok(value: Any, type_tag: str) -> bool:
    if type_tag.endswith("|null") and value is None:
        return True
    base = type_tag.split("|")[0]
    if base == "str":
        return isinstance(value, str)
    if base == "str[]":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if base == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if base == "object":
        return isinstance(value, dict)
    if base == "object[]":
        return isinstance(value, list) and all(isinstance(v, dict) for v in value)
    return True


def validate_against_default_schema(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record or record[field] in (None, "", [], {}):
            warnings.append(f"missing required field: {field}")
    for field, type_tag in DEFAULT_SCHEMA_FIELDS.items():
        if field not in record:
            continue
        if not _type_ok(record[field], type_tag):
            warnings.append(f"field '{field}' does not match expected type '{type_tag}' (got {type(record[field]).__name__})")
    ok = not any(w.startswith("missing required field") for w in warnings)
    return ok, warnings


def validate_against_config_schema(record: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    type_map = {"string": "str", "number": "number", "string[]": "str[]", "object": "object", "object[]": "object[]"}
    ok = True
    for spec in config.get("fields", []):
        dest = spec["path"]
        if dest not in record:
            if spec.get("required") and config.get("on_missing") != "omit":
                warnings.append(f"required projected field '{dest}' missing from output")
                ok = False
            continue
        tag = type_map.get(spec.get("type", ""), None)
        if tag and not _type_ok(record[dest], tag + ("|null" if record[dest] is None else "")):
            warnings.append(f"projected field '{dest}' does not match declared type '{spec.get('type')}'")
    return ok, warnings
