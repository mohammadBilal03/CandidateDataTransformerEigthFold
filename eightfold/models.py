"""Core data models shared across the pipeline."""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RawField:
    """One atomic piece of information extracted from a single source,
    before normalization or merging. This is the common currency every
    adapter speaks, so source-specific quirks never leak past extraction.
    """
    candidate_key: str          # best-effort identity key from THIS source alone
    field: str                  # canonical field name this raw value maps to, e.g. "emails", "phones", "skills"
    value: Any                  # the raw (not-yet-normalized) value
    source: str                 # e.g. "recruiter_csv", "ats_json", "github", "linkedin", "resume", "notes"
    method: str                 # how it was obtained, e.g. "csv_column:email", "regex:phone", "api:bio"
    raw_confidence: float = 1.0 # source-local confidence in the *extraction* (not normalization) of this value


@dataclass
class NormalizedField(RawField):
    """A RawField after normalization has run. normalized_value is the
    canonical-format value; value retains the original raw value for
    provenance/debugging. norm_confidence may differ from raw_confidence
    if normalization degraded certainty (e.g. unparseable date).
    """
    normalized_value: Any = None
    norm_confidence: float = 1.0
    norm_error: Optional[str] = None
