"""Base adapter interface + source-type detection.

Detection deliberately works off cheap, local signals (file extension +
a peek at content) rather than anything that could fail destructively on
a garbage file. Every adapter's extract() must be defensive: a malformed
or empty source should yield zero RawFields, never an exception that
kills the whole run.
"""
from __future__ import annotations
import json
import os
from typing import List
from ..models import RawField


class BaseAdapter:
    source_name: str = "base"

    def extract(self, path_or_value: str) -> List[RawField]:
        raise NotImplementedError


def sniff_source_type(path: str) -> str:
    """Returns one of: recruiter_csv, ats_json, github, linkedin, resume, notes, unknown."""
    lower = path.lower()

    if lower.startswith("http://") or lower.startswith("https://"):
        if "github.com" in lower:
            return "github"
        if "linkedin.com" in lower:
            return "linkedin"
        return "unknown"

    if not os.path.exists(path):
        return "unknown"

    ext = os.path.splitext(lower)[1]
    if ext == ".csv":
        return "recruiter_csv"
    if ext == ".json":
        # ATS json vs. a saved linkedin/github json export -- peek at keys.
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return "unknown"
        sample = data[0] if isinstance(data, list) and data else data
        if isinstance(sample, dict):
            keys = {k.lower() for k in sample.keys()}
            if {"login", "public_repos"} & keys:
                return "github"
            if {"headline", "experience", "education"} & keys and "repos" not in keys:
                return "linkedin"
        return "ats_json"
    if ext in (".pdf", ".docx"):
        return "resume"
    if ext == ".txt":
        return "notes"
    return "unknown"
