"""Per-field normalizers. Each takes a raw value (+ optional context like a
default region for phone parsing) and returns (normalized_value, confidence,
error). Normalizers NEVER raise on bad input -- a value that can't be
normalized degrades to (None, 0.0, "reason") rather than crashing the run,
per the "missing/garbage source must not crash" constraint.
"""
import re
from datetime import datetime
from typing import Optional, Tuple

try:
    import phonenumbers
    _HAS_PHONENUMBERS = True
except ImportError:
    _HAS_PHONENUMBERS = False

# --- country -----------------------------------------------------------

_COUNTRY_ALIASES = {
    "united states": "US", "usa": "US", "u.s.a.": "US", "u.s.": "US", "us": "US",
    "united states of america": "US",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "england": "GB",
    "india": "IN", "canada": "CA", "germany": "DE", "france": "FR",
    "australia": "AU", "singapore": "SG", "netherlands": "NL",
    "ireland": "IE", "spain": "ES", "italy": "IT", "brazil": "BR",
    "japan": "JP", "china": "CN", "mexico": "MX",
}


def normalize_country(value) -> Tuple[Optional[str], float, Optional[str]]:
    if not value or not isinstance(value, str):
        return None, 0.0, "empty_or_non_string"
    v = value.strip()
    if not v:
        return None, 0.0, "empty"
    if len(v) == 2 and v.isalpha():
        return v.upper(), 0.95, None
    key = v.lower()
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key], 0.9, None
    return None, 0.2, f"unrecognized_country:{value}"


# --- phone (E.164) -------------------------------------------------------

def normalize_phone(value, default_region: Optional[str] = None) -> Tuple[Optional[str], float, Optional[str]]:
    if not value or not isinstance(value, str):
        return None, 0.0, "empty_or_non_string"
    raw = value.strip()
    if not raw:
        return None, 0.0, "empty"

    if _HAS_PHONENUMBERS:
        regions_to_try = [default_region, "US", None]
        for region in regions_to_try:
            try:
                parsed = phonenumbers.parse(raw, region)
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), 0.95, None
            except Exception:
                continue
        return None, 0.1, f"unparseable_phone:{raw}"

    # Fallback heuristic if phonenumbers isn't installed.
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+") and 8 <= len(digits) <= 16:
        return digits, 0.5, None
    only_digits = re.sub(r"\D", "", raw)
    if len(only_digits) == 10:
        return f"+1{only_digits}", 0.4, None
    return None, 0.1, f"unparseable_phone:{raw}"


# --- date (YYYY-MM) -------------------------------------------------------

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"]) if m}
_MONTHS.update({m[:3].lower(): i for m, i in list(_MONTHS.items())})

_DATE_PATTERNS = [
    (re.compile(r"^(?P<y>\d{4})-(?P<m>\d{1,2})(-\d{1,2})?$"), None),
    (re.compile(r"^(?P<m>\d{1,2})/(?P<y>\d{4})$"), None),
    (re.compile(r"^(?P<mon>[A-Za-z]+)\.?\s+(?P<y>\d{4})$"), "month_name"),
    (re.compile(r"^(?P<y>\d{4})$"), "year_only"),
]


def normalize_date(value) -> Tuple[Optional[str], float, Optional[str]]:
    """Best-effort parse to YYYY-MM. Recognizes 'present'/'current' as a
    sentinel meaning ongoing (kept as the literal string 'present')."""
    if value is None:
        return None, 0.0, "empty"
    if isinstance(value, str) and value.strip().lower() in ("present", "current", "now", "ongoing"):
        return "present", 0.9, None
    if not isinstance(value, str):
        return None, 0.0, "non_string"
    raw = value.strip()
    if not raw:
        return None, 0.0, "empty"

    for pattern, kind in _DATE_PATTERNS:
        m = pattern.match(raw)
        if not m:
            continue
        try:
            if kind == "month_name":
                mon = _MONTHS.get(m.group("mon").lower())
                if not mon:
                    continue
                return f"{m.group('y')}-{mon:02d}", 0.85, None
            if kind == "year_only":
                return f"{m.group('y')}-01", 0.5, "year_only_assumed_january"
            y, mo = m.group("y"), int(m.group("m"))
            if 1 <= mo <= 12:
                return f"{y}-{mo:02d}", 0.9, None
        except Exception:
            continue

    # last resort: try a few strptime formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %Y", "%b %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt.year:04d}-{dt.month:02d}", 0.7, None
        except ValueError:
            continue

    return None, 0.1, f"unparseable_date:{raw}"


# --- skills (canonical names) ---------------------------------------------

_SKILL_SYNONYMS = {
    "js": "javascript", "javascript": "javascript", "node": "node.js", "nodejs": "node.js",
    "node.js": "node.js", "ts": "typescript", "typescript": "typescript",
    "py": "python", "python": "python", "py3": "python",
    "golang": "go", "go": "go",
    "k8s": "kubernetes", "kubernetes": "kubernetes",
    "postgres": "postgresql", "postgresql": "postgresql", "psql": "postgresql",
    "ml": "machine learning", "machine learning": "machine learning",
    "ai": "artificial intelligence",
    "reactjs": "react", "react.js": "react", "react": "react",
    "c++": "c++", "cpp": "c++",
    "c#": "c#", "csharp": "c#",
    "aws": "aws", "amazon web services": "aws",
    "gcp": "gcp", "google cloud": "gcp", "google cloud platform": "gcp",
}


def normalize_skill(value) -> Tuple[Optional[str], float, Optional[str]]:
    if not value or not isinstance(value, str):
        return None, 0.0, "empty_or_non_string"
    raw = value.strip()
    if not raw:
        return None, 0.0, "empty"
    key = raw.lower()
    if key in _SKILL_SYNONYMS:
        return _SKILL_SYNONYMS[key], 0.95, None
    # generic fallback: lowercase + strip punctuation noise
    cleaned = re.sub(r"\s+", " ", key).strip(" .,-")
    if not cleaned:
        return None, 0.1, "empty_after_clean"
    return cleaned, 0.6, None


# --- name / generic string -------------------------------------------------

def normalize_name(value) -> Tuple[Optional[str], float, Optional[str]]:
    if not value or not isinstance(value, str):
        return None, 0.0, "empty_or_non_string"
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return None, 0.0, "empty"
    return cleaned, 0.9, None


def normalize_email(value) -> Tuple[Optional[str], float, Optional[str]]:
    if not value or not isinstance(value, str):
        return None, 0.0, "empty_or_non_string"
    cleaned = value.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
        return None, 0.1, f"malformed_email:{value}"
    return cleaned, 0.95, None
