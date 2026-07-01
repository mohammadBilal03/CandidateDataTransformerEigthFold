"""Resume file adapter -- unstructured prose source (PDF or DOCX).

Resumes have no fixed schema, so extraction here is regex/heuristic-based:
email & phone via pattern match, name via "first non-empty line that looks
like a name", skills via matching tokens against the same synonym table the
normalizer uses. This is intentionally light-weight; a production system
would likely use an NLP/LLM-based extractor here, but kept deterministic per
the "deterministic & explainable" constraint and to avoid an external
dependency.
"""
import re
from typing import List
from ..models import RawField
from ..normalize import _SKILL_SYNONYMS
from .base import BaseAdapter

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d().\-\s]{7,}\d)")


def _extract_text(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".pdf"):
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except Exception:
            return ""
    if lower.endswith(".docx"):
        try:
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            return ""
    return ""


class ResumeAdapter(BaseAdapter):
    source_name = "resume"

    def extract(self, path: str) -> List[RawField]:
        text = _extract_text(path)
        if not text.strip():
            return []  # unreadable/scanned/garbage resume -> no fields, no crash

        fields: List[RawField] = []
        emails = _EMAIL_RE.findall(text)
        candidate_key = emails[0].lower() if emails else path

        for email in dict.fromkeys(emails):  # dedupe, preserve order
            fields.append(RawField(candidate_key, "emails", email, self.source_name, "regex:email", 0.7))

        for phone in dict.fromkeys(m.strip() for m in _PHONE_RE.findall(text)):
            digit_count = sum(c.isdigit() for c in phone)
            if 7 <= digit_count <= 15:
                fields.append(RawField(candidate_key, "phones", phone, self.source_name, "regex:phone", 0.55))

        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if first_line and 2 <= len(first_line.split()) <= 5 and not _EMAIL_RE.search(first_line):
            fields.append(RawField(candidate_key, "full_name", first_line, self.source_name, "heuristic:first_line", 0.4))

        lower_text = text.lower()
        for token, canonical in _SKILL_SYNONYMS.items():
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", lower_text):
                fields.append(RawField(candidate_key, "skills", canonical, self.source_name, "keyword_match:skills", 0.5))

        linkedin_match = re.search(r"linkedin\.com/in/[A-Za-z0-9-_/]+", text)
        if linkedin_match:
            fields.append(RawField(candidate_key, "links.linkedin", "https://" + linkedin_match.group(0), self.source_name, "regex:linkedin_url", 0.7))
        github_match = re.search(r"github\.com/[A-Za-z0-9-_/]+", text)
        if github_match:
            fields.append(RawField(candidate_key, "links.github", "https://" + github_match.group(0), self.source_name, "regex:github_url", 0.7))

        return fields
