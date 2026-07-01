"""LinkedIn profile adapter -- unstructured source.

IMPORTANT ASSUMPTION (documented in README): LinkedIn does not offer a public,
unauthenticated REST/GraphQL API like GitHub does, and scraping linkedin.com
directly violates their ToS and isn't reachable from this sandboxed network.
This adapter therefore expects a LOCAL JSON FILE that represents an already
-fetched/exported profile (e.g. via LinkedIn's official Member Data export,
or a partner API response normalized to this shape upstream). If given a bare
https://linkedin.com/... URL with no matching local export, it degrades
gracefully to zero RawFields (consistent with "missing source must not
crash") rather than pretending to scrape.

Expected export shape (flexible/partial):
{
  "name": "...", "headline": "...",
  "location": "City, Region, Country",
  "experience": [{"company": "...", "title": "...", "start": "...", "end": "...", "description": "..."}],
  "education": [{"school": "...", "degree": "...", "field": "...", "end_year": "..."}],
  "skills": ["...", "..."]
}
"""
import json
import os
from typing import List
from ..models import RawField
from .base import BaseAdapter


class LinkedInAdapter(BaseAdapter):
    source_name = "linkedin"

    def extract(self, path_or_url: str) -> List[RawField]:
        if path_or_url.startswith("http"):
            # No reachable public API / scraping path in this environment -- see docstring.
            return []
        if not os.path.exists(path_or_url):
            return []
        try:
            with open(path_or_url, "r", encoding="utf-8") as f:
                profile = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(profile, dict):
            return []

        candidate_key = profile.get("public_url") or profile.get("name") or path_or_url
        fields: List[RawField] = []

        if profile.get("name"):
            fields.append(RawField(candidate_key, "full_name", profile["name"], self.source_name, "export:name", 0.85))
        if profile.get("headline"):
            fields.append(RawField(candidate_key, "headline", profile["headline"], self.source_name, "export:headline", 0.85))
        if profile.get("location"):
            parts = [p.strip() for p in str(profile["location"]).split(",")]
            if len(parts) >= 1:
                fields.append(RawField(candidate_key, "location.city", parts[0], self.source_name, "export:location", 0.6))
            if len(parts) >= 2:
                fields.append(RawField(candidate_key, "location.region", parts[1], self.source_name, "export:location", 0.6))
            if len(parts) >= 3:
                fields.append(RawField(candidate_key, "location.country", parts[2], self.source_name, "export:location", 0.6))
        if profile.get("public_url"):
            fields.append(RawField(candidate_key, "links.linkedin", profile["public_url"], self.source_name, "export:url", 0.95))

        for exp in profile.get("experience", []) if isinstance(profile.get("experience"), list) else []:
            if isinstance(exp, dict):
                fields.append(RawField(candidate_key, "experience", exp, self.source_name, "export:experience[]", 0.85))

        for edu in profile.get("education", []) if isinstance(profile.get("education"), list) else []:
            if isinstance(edu, dict):
                mapped_edu = dict(edu)
                if "school" in mapped_edu and "institution" not in mapped_edu:
                    mapped_edu["institution"] = mapped_edu.pop("school")
                fields.append(RawField(candidate_key, "education", mapped_edu, self.source_name, "export:education[]", 0.85))

        for skill in profile.get("skills", []) if isinstance(profile.get("skills"), list) else []:
            if skill:
                fields.append(RawField(candidate_key, "skills", skill, self.source_name, "export:skills[]", 0.75))

        years = profile.get("years_experience")
        if years is not None:
            fields.append(RawField(candidate_key, "years_experience", years, self.source_name, "export:years_experience", 0.7))

        return fields
