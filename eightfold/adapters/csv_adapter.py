"""Recruiter CSV export adapter -- structured source.

Expected loose shape: rows with name, email, phone, current_company, title
columns (header names may vary in case/spacing; we fuzzy-match common
aliases since "the same person may appear in several sources with
conflicting/differently-named fields").
"""
import csv
from typing import List
from ..models import RawField
from .base import BaseAdapter

_HEADER_ALIASES = {
    "name": "full_name", "full_name": "full_name", "candidate_name": "full_name",
    "email": "emails", "email_address": "emails",
    "phone": "phones", "phone_number": "phones", "mobile": "phones",
    "current_company": "experience.company", "company": "experience.company",
    "title": "experience.title", "current_title": "experience.title", "job_title": "experience.title",
}


class RecruiterCSVAdapter(BaseAdapter):
    source_name = "recruiter_csv"

    def extract(self, path: str) -> List[RawField]:
        fields: List[RawField] = []
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return fields
                colmap = {}
                for raw_header in reader.fieldnames:
                    key = raw_header.strip().lower().replace(" ", "_")
                    if key in _HEADER_ALIASES:
                        colmap[raw_header] = _HEADER_ALIASES[key]

                for row_idx, row in enumerate(reader):
                    # candidate_key: prefer email, else row index (best-effort identity within this source)
                    email_col = next((h for h, mapped in colmap.items() if mapped == "emails"), None)
                    row_email = (row.get(email_col) or "").strip().lower() if email_col else ""
                    candidate_key = row_email or f"csv_row_{row_idx}"

                    for raw_header, mapped_field in colmap.items():
                        value = row.get(raw_header)
                        if value is None or not str(value).strip():
                            continue  # missing cell -> simply no RawField, never invented
                        fields.append(RawField(
                            candidate_key=candidate_key,
                            field=mapped_field,
                            value=str(value).strip(),
                            source=self.source_name,
                            method=f"csv_column:{raw_header}",
                            raw_confidence=0.95,
                        ))
        except (FileNotFoundError, csv.Error, UnicodeDecodeError, PermissionError):
            return []  # malformed/missing source must not crash the run
        return fields
