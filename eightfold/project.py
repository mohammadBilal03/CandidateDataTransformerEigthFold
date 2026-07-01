"""Projection layer.

Applies a runtime config to a canonical candidate record, producing a
reshaped output WITHOUT mutating the canonical record itself. This keeps
"internal canonical record" and "projection layer" cleanly separated, as
required: the same canonical engine output can be projected through any
number of different configs.

Config shape (see SKILL/problem statement example):
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": true,
  "on_missing": "null"   // "null" | "omit" | "error"
}
"""
import re
from typing import Any, Dict, List, Tuple

from .normalize import normalize_phone, normalize_skill, normalize_country, normalize_date

_ARRAY_INDEX_RE = re.compile(r"^(?P<base>[^\[\]]+)\[(?P<idx>\d*)\]$")


class MissingValueError(Exception):
    pass


def _resolve_path(record: Dict[str, Any], path: str) -> Tuple[Any, bool]:
    """Resolves a dotted/bracketed path like 'skills[].name' or 'emails[0]'
    against the canonical record. Returns (value, found)."""
    parts = path.split(".")
    current: Any = record
    for i, part in enumerate(parts):
        m = _ARRAY_INDEX_RE.match(part)
        if m:
            base, idx = m.group("base"), m.group("idx")
            if not isinstance(current, dict) or base not in current:
                return None, False
            current = current[base]
            if not isinstance(current, list):
                return None, False
            if idx == "":
                remainder = ".".join(parts[i + 1:])
                if not remainder:
                    return current, True
                out = []
                for item in current:
                    sub_val, found = _resolve_path(item if isinstance(item, dict) else {"_": item}, remainder)
                    if found:
                        out.append(sub_val)
                return out, True
            else:
                idx = int(idx)
                if idx >= len(current):
                    return None, False
                current = current[idx]
        else:
            if not isinstance(current, dict) or part not in current:
                return None, False
            current = current[part]
    return current, current is not None


_NORMALIZERS = {
    "E164": lambda v: normalize_phone(v)[0] if v else None,
    "canonical": lambda v: normalize_skill(v)[0] if isinstance(v, str) else v,
    "iso2": lambda v: normalize_country(v)[0] if v else None,
    "yyyy-mm": lambda v: normalize_date(v)[0] if v else None,
}


def _apply_normalize(value: Any, normalize: str) -> Any:
    fn = _NORMALIZERS.get(normalize)
    if not fn:
        return value
    if isinstance(value, list):
        return [fn(v) for v in value]
    return fn(value)


def _set_path(out: Dict[str, Any], dest_path: str, value: Any):
    parts = dest_path.split(".")
    current = out
    for p in parts[:-1]:
        current = current.setdefault(p, {})
    current[parts[-1]] = value


def project(canonical: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Applies `config` to one canonical candidate record. Raises
    MissingValueError if on_missing == "error" and a required value is
    absent (caller decides whether that fails the whole run or just the
    record)."""
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", False)
    out: Dict[str, Any] = {}

    for spec in config.get("fields", []):
        dest = spec["path"]
        src_path = spec.get("from", dest)
        required = spec.get("required", False)

        value, found = _resolve_path(canonical, src_path)

        if spec.get("normalize") and found:
            value = _apply_normalize(value, spec["normalize"])
            found = value not in (None, [], "")

        if not found:
            if on_missing == "error" and required:
                raise MissingValueError(f"required field '{dest}' (from '{src_path}') is missing")
            if on_missing == "omit":
                continue
            value = None

        _set_path(out, dest, value)

        if include_confidence:
            top_field = src_path.split("[")[0].split(".")[0]
            _set_path(out, f"{dest}__confidence", {
                "source_field": top_field,
                "candidate_overall_confidence": canonical.get("overall_confidence"),
            })

    return out


def project_all(canonicals: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for c in canonicals:
        try:
            results.append(project(c, config))
        except MissingValueError as e:
            results.append({"_error": str(e), "candidate_id": c.get("candidate_id")})
    return results
