"""Pipeline orchestrator. This is the only module that wires the stages
together; everything else stays independently testable.
"""
from typing import Any, Dict, List, Optional

from .adapters.base import sniff_source_type
from .adapters.csv_adapter import RecruiterCSVAdapter
from .adapters.ats_json_adapter import ATSJsonAdapter
from .adapters.github_adapter import GitHubAdapter
from .adapters.linkedin_adapter import LinkedInAdapter
from .adapters.resume_adapter import ResumeAdapter
from .adapters.notes_adapter import NotesAdapter
from .merge import merge_all
from .project import project_all
from .validate import validate_against_default_schema, validate_against_config_schema
from .models import RawField

_ADAPTERS = {
    "recruiter_csv": RecruiterCSVAdapter(),
    "ats_json": ATSJsonAdapter(),
    "github": GitHubAdapter(),
    "linkedin": LinkedInAdapter(),
    "resume": ResumeAdapter(),
    "notes": NotesAdapter(),
}


def run_pipeline(inputs: List[str], config: Optional[Dict[str, Any]] = None,
                  source_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """inputs: list of file paths and/or URLs (GitHub/LinkedIn).
    config: optional runtime output config (see project.py).
    source_overrides: optional {input: source_type} to bypass auto-detection.

    Returns {"profiles": [...], "warnings": [...], "stats": {...}}.
    """
    source_overrides = source_overrides or {}
    all_fields: List[RawField] = []
    warnings: List[str] = []
    stats = {"inputs_processed": 0, "inputs_skipped": 0, "fields_extracted": 0}

    for raw_input in inputs:
        source_type = source_overrides.get(raw_input) or sniff_source_type(raw_input)
        adapter = _ADAPTERS.get(source_type)
        if not adapter:
            warnings.append("could not determine source type for '%s'; skipped" % raw_input)
            stats["inputs_skipped"] += 1
            continue
        try:
            fields = adapter.extract(raw_input)
        except Exception as e:
            warnings.append("adapter '%s' raised on '%s': %s; skipped" % (source_type, raw_input, e))
            stats["inputs_skipped"] += 1
            continue
        if not fields:
            warnings.append("no usable data extracted from '%s' (source_type=%s)" % (raw_input, source_type))
        all_fields.extend(fields)
        stats["inputs_processed"] += 1
        stats["fields_extracted"] += len(fields)

    canonical_profiles = merge_all(all_fields)

    output_profiles = []
    for profile in canonical_profiles:
        if config:
            projected = project_all([profile], config)[0]
            ok, val_warnings = validate_against_config_schema(projected, config)
            output_profiles.append(projected)
        else:
            ok, val_warnings = validate_against_default_schema(profile)
            output_profiles.append(profile)
        for w in val_warnings:
            warnings.append("[%s] %s" % (profile.get('candidate_id'), w))

    return {"profiles": output_profiles, "warnings": warnings, "stats": stats}
