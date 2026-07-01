"""GitHub profile adapter -- unstructured source via the public REST API.
Accepts either a profile URL (https://github.com/<user>) or a bare username.
Pulls name, bio (-> headline), and repo languages (-> skills). Network calls
are wrapped defensively: a missing user, rate limit, or network failure
degrades to zero RawFields rather than crashing the run.
"""
import json
import re
import urllib.request
import urllib.error
from typing import List
from ..models import RawField
from .base import BaseAdapter


def _get_json(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": "eightfold-ingest/1.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _username_from(value: str) -> str:
    value = value.strip()
    m = re.search(r"github\.com/([A-Za-z0-9-]+)", value)
    return m.group(1) if m else value.strip("/ ")


class GitHubAdapter(BaseAdapter):
    source_name = "github"

    def extract(self, url_or_username: str) -> List[RawField]:
        username = _username_from(url_or_username)
        if not username:
            return []
        fields: List[RawField] = []
        try:
            profile = _get_json(f"https://api.github.com/users/{username}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
            return []
        if not isinstance(profile, dict) or profile.get("message") == "Not Found":
            return []

        candidate_key = f"github:{username}"

        if profile.get("name"):
            fields.append(RawField(candidate_key, "full_name", profile["name"], self.source_name, "api:name", 0.5))
        if profile.get("bio"):
            fields.append(RawField(candidate_key, "headline", profile["bio"], self.source_name, "api:bio", 0.5))
        if profile.get("email"):
            fields.append(RawField(candidate_key, "emails", profile["email"], self.source_name, "api:email", 0.4))
        if profile.get("blog"):
            fields.append(RawField(candidate_key, "links.portfolio", profile["blog"], self.source_name, "api:blog", 0.5))
        if profile.get("location"):
            fields.append(RawField(candidate_key, "location.city", profile["location"], self.source_name, "api:location", 0.4))
        fields.append(RawField(candidate_key, "links.github", f"https://github.com/{username}", self.source_name, "derived:url", 0.99))

        try:
            repos = _get_json(f"https://api.github.com/users/{username}/repos?per_page=100&sort=pushed")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
            repos = []
        languages = set()
        for repo in repos if isinstance(repos, list) else []:
            if isinstance(repo, dict) and repo.get("language"):
                languages.add(repo["language"])
        for lang in languages:
            fields.append(RawField(candidate_key, "skills", lang, self.source_name, "api:repo_language", 0.6))

        return fields
