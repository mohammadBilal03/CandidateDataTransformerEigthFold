"""ATS JSON blob adapter -- structured source whose field names do NOT
match ours (the spec calls this out explicitly), so this adapter's only
job is mapping ATS-specific keys to canonical RawFields. Built to tolerate
a top-level list, a top-level dict with a "candidates" key, or a single
candidate dict.
"""
import json
from typing import List, Any, Dict
from ..models import RawField
from .base import BaseAdapter

# ATS key -> canonical field. Multiple ATS aliases map to the same canonical field
# since different ATS exports name things differently.
_KEY_MAP = {
    "fullname": "full_name", "full_name": "full_name", "name": "full_name", "candidatename": "full_name",
    "emailaddr": "emails", "email": "emails", "email_address": "emails",
    "mobileno": "phones", "phone": "phones", "phonenumber": "phones",
    "resumeheadline": "headline", "headline": "headline", "summary": "headline",
    "city": "location.city", "region": "location.region", "state": "location.region", "country": "location.country",
}

_EXPERIENCE_LIST_KEYS = {"workhistory", "experience", "employment"}
_EXPERIENCE_KEY_MAP = {
    "employer": "company", "company": "company",
    "role": "title", "title": "title", "position": "title",
    "from": "start", "start": "start", "startdate": "start",
    "to": "end", "end": "end", "enddate": "end",
    "description": "summary", "summary": "summary",
}
_EDUCATION_LIST_KEYS = {"schools", "education"}
_EDUCATION_KEY_MAP = {
    "name": "institution", "institution": "institution", "school": "institution",
    "degree": "degree",
    "fieldofstudy": "field", "field": "field", "major": "field",
    "graduationyear": "end_year", "endyear": "end_year", "year": "end_year",
}


def _norm_key(k: str) -> str:
    return k.strip().lower().replace(" ", "").replace("_", "")


class ATSJsonAdapter(BaseAdapter):
    source_name = "ats_json"

    def extract(self, path: str) -> List[RawField]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return []

        if isinstance(data, dict) and "candidates" in data and isinstance(data["candidates"], list):
            records = data["candidates"]
        elif isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            return []

        fields: List[RawField] = []
        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            fields.extend(self._extract_one(record, idx))
        return fields

    def _extract_one(self, record: Dict[str, Any], idx: int) -> List[RawField]:
        out: List[RawField] = []
        flat: Dict[str, Any] = {}
        self._flatten(record, flat)

        candidate_key = None
        for k, v in flat.items():
            if _norm_key(k.split(".")[-1]) in ("email", "emailaddr", "email_address") and v:
                candidate_key = str(v).strip().lower()
                break
        candidate_key = candidate_key or record.get("id") or f"ats_row_{idx}"

        for raw_key, value in flat.items():
            leaf = raw_key.split(".")[-1]
            norm_leaf = _norm_key(leaf)
            if norm_leaf in _KEY_MAP and value not in (None, "", [], {}):
                out.append(RawField(
                    candidate_key=str(candidate_key), field=_KEY_MAP[norm_leaf],
                    value=value, source=self.source_name, method=f"ats_key:{raw_key}",
                    raw_confidence=0.9,
                ))

        for list_key in _EXPERIENCE_LIST_KEYS:
            items = self._find_list(record, list_key)
            for item in items:
                if not isinstance(item, dict):
                    continue
                mapped = {_EXPERIENCE_KEY_MAP.get(_norm_key(k)): v for k, v in item.items()}
                mapped.pop(None, None)
                if mapped:
                    out.append(RawField(
                        candidate_key=str(candidate_key), field="experience", value=mapped,
                        source=self.source_name, method=f"ats_key:{list_key}[]", raw_confidence=0.85,
                    ))

        for list_key in _EDUCATION_LIST_KEYS:
            items = self._find_list(record, list_key)
            for item in items:
                if not isinstance(item, dict):
                    continue
                mapped = {_EDUCATION_KEY_MAP.get(_norm_key(k)): v for k, v in item.items()}
                mapped.pop(None, None)
                if mapped:
                    out.append(RawField(
                        candidate_key=str(candidate_key), field="education", value=mapped,
                        source=self.source_name, method=f"ats_key:{list_key}[]", raw_confidence=0.85,
                    ))
        return out

    def _find_list(self, record: Dict[str, Any], target_key: str):
        for k, v in record.items():
            if _norm_key(k) == target_key and isinstance(v, list):
                return v
        return []

    def _flatten(self, obj: Any, out: Dict[str, Any], prefix: str = ""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if _norm_key(k) in _EXPERIENCE_LIST_KEYS or _norm_key(k) in _EDUCATION_LIST_KEYS:
                    continue  # handled separately as list fields
                path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    self._flatten(v, out, path)
                elif not isinstance(v, list):
                    out[path] = v
