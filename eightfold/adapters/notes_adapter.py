"""Recruiter notes adapter -- freeform .txt source.

Lowest-trust source (see trust.py): useful for corroboration and the
occasional contact detail a recruiter jotted down, but never an
authoritative winner on its own. Uses the same lightweight regex
heuristics as the resume adapter.
"""
import re
from typing import List
from ..models import RawField
from .base import BaseAdapter
from .resume_adapter import _EMAIL_RE, _PHONE_RE


class NotesAdapter(BaseAdapter):
    source_name = "notes"

    def extract(self, path: str) -> List[RawField]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except (FileNotFoundError, PermissionError, UnicodeDecodeError):
            return []
        if not text.strip():
            return []

        fields: List[RawField] = []
        emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
        candidate_key = emails[0].lower() if emails else path

        for email in emails:
            fields.append(RawField(candidate_key, "emails", email, self.source_name, "regex:email", 0.5))
        for phone in dict.fromkeys(m.strip() for m in _PHONE_RE.findall(text)):
            digit_count = sum(c.isdigit() for c in phone)
            if 7 <= digit_count <= 15:
                fields.append(RawField(candidate_key, "phones", phone, self.source_name, "regex:phone", 0.4))

        first_sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0]
        if first_sentence and len(first_sentence.split()) <= 30:
            fields.append(RawField(candidate_key, "headline", first_sentence.strip(), self.source_name, "heuristic:first_sentence", 0.25))

        return fields
