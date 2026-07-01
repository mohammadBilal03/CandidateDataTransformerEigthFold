"""Canonical output schema (the default, full schema from the problem
statement) expressed as a light-weight structure we can validate against
without pulling in a full JSON-Schema implementation.
"""

# field -> "type" tag used by validate.py. Kept intentionally simple:
# str, str[], number, number|null, object, object[], any
DEFAULT_SCHEMA_FIELDS = {
    "candidate_id": "str",
    "full_name": "str|null",
    "emails": "str[]",
    "phones": "str[]",
    "location": "object|null",       # {city, region, country}
    "links": "object",               # {linkedin, github, portfolio, other[]}
    "headline": "str|null",
    "years_experience": "number|null",
    "skills": "object[]",            # [{name, confidence, sources[]}]
    "experience": "object[]",        # [{company, title, start, end, summary}]
    "education": "object[]",         # [{institution, degree, field, end_year}]
    "provenance": "object[]",        # [{field, source, method}]
    "overall_confidence": "number",
}

REQUIRED_FIELDS = {"candidate_id", "emails"}
