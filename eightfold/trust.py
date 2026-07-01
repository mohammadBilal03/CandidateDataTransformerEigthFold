"""Static trust configuration.

Trust scores are intentionally simple (0-1 floats per source, with optional
per-field overrides) rather than a learned model -- the prompt asks for a
deterministic, explainable system, and a transparent lookup table is the
most explainable thing that still gives sensible behavior:

  - Recruiter CSV / ATS are human-entered or HR-system-of-record data, so
    they win on contact/identity fields (name, email, phone, current title).
  - LinkedIn / resume are self-reported but structured around career history,
    so they win on experience/education.
  - GitHub is the most reliable for skills/tech signal since it's derived
    from actual repos, but unreliable for identity (bios are often empty or
    jokey) and useless for experience/education.
  - Recruiter notes are freeform human commentary: useful corroboration,
    never an authoritative winner on its own.
"""

DEFAULT_SOURCE_TRUST = {
    "recruiter_csv": 0.95,
    "ats_json": 0.9,
    "linkedin": 0.8,
    "github": 0.6,
    "resume": 0.75,
    "notes": 0.4,
}

# field -> {source: override_trust}. Anything not listed uses DEFAULT_SOURCE_TRUST.
FIELD_TRUST_OVERRIDES = {
    "full_name": {"recruiter_csv": 0.95, "ats_json": 0.9, "linkedin": 0.85, "resume": 0.7, "github": 0.4, "notes": 0.3},
    "emails": {"recruiter_csv": 0.97, "ats_json": 0.92, "linkedin": 0.5, "resume": 0.6, "github": 0.3, "notes": 0.3},
    "phones": {"recruiter_csv": 0.97, "ats_json": 0.92, "linkedin": 0.3, "resume": 0.6, "github": 0.1, "notes": 0.3},
    "headline": {"linkedin": 0.9, "ats_json": 0.6, "recruiter_csv": 0.6, "resume": 0.7, "github": 0.3, "notes": 0.2},
    "skills": {"github": 0.85, "linkedin": 0.75, "resume": 0.7, "ats_json": 0.3, "recruiter_csv": 0.2, "notes": 0.3},
    "experience": {"linkedin": 0.9, "resume": 0.85, "ats_json": 0.5, "recruiter_csv": 0.3, "github": 0.2, "notes": 0.2},
    "education": {"linkedin": 0.9, "resume": 0.85, "ats_json": 0.4, "recruiter_csv": 0.2, "github": 0.1, "notes": 0.2},
    "location": {"linkedin": 0.85, "recruiter_csv": 0.7, "ats_json": 0.6, "resume": 0.5, "github": 0.5, "notes": 0.3},
    "links": {"recruiter_csv": 0.9, "ats_json": 0.85, "linkedin": 0.95, "resume": 0.7, "github": 0.95, "notes": 0.5},
    "years_experience": {"linkedin": 0.85, "resume": 0.8, "ats_json": 0.5, "recruiter_csv": 0.4, "github": 0.2, "notes": 0.3},
}

# Relative importance of each field when rolling up overall_confidence.
FIELD_WEIGHTS = {
    "full_name": 1.0,
    "emails": 1.0,
    "phones": 0.6,
    "location": 0.5,
    "links": 0.4,
    "headline": 0.4,
    "years_experience": 0.5,
    "skills": 0.7,
    "experience": 0.8,
    "education": 0.5,
}


def trust_for(field: str, source: str) -> float:
    return FIELD_TRUST_OVERRIDES.get(field, {}).get(source, DEFAULT_SOURCE_TRUST.get(source, 0.3))
