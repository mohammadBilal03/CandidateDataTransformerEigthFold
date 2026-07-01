"""Merge engine.

Two responsibilities, kept separate:
  1. group_by_identity(): link RawFields across sources/adapters into one
     bucket per real-world candidate (the match-key policy from the design).
  2. merge_candidate(): given one candidate's RawFields, normalize +
     pick winners + assemble the canonical record + compute confidence.
"""
from collections import defaultdict
from typing import Dict, List, Any
import re
import uuid
from difflib import SequenceMatcher

from .models import RawField
from .normalize import (
    normalize_phone, normalize_date, normalize_skill, normalize_country,
    normalize_name, normalize_email,
)
from .trust import trust_for, FIELD_WEIGHTS

SINGLE_VALUE_FIELDS = {"full_name", "headline", "years_experience"}
LIST_FIELDS = {"emails", "phones", "skills", "experience", "education"}
NESTED_FIELDS = {"location", "links"}


def _email_key(v: str) -> str:
    ok, conf, _ = normalize_email(v) if isinstance(v, str) else (None, 0, None)
    return ok or (v or "").strip().lower()


def _phone_key(v: str) -> str:
    ok, conf, _ = normalize_phone(v) if isinstance(v, str) else (None, 0, None)
    return ok or (v or "").strip()


def group_by_identity(all_fields: List[RawField]) -> List[List[RawField]]:
    """Links RawFields into per-candidate buckets.

    Match key priority: normalized email > normalized phone > fuzzy
    full_name token match. Fields are first grouped by their *source-local*
    candidate_key (fields from literally the same source row already belong
    together), then those per-source groups are merged across sources when
    their email/phone/name overlap.
    """
    # Step 1: bucket by (source, candidate_key) -- fields from the same row/profile.
    local_groups: Dict[Any, List[RawField]] = defaultdict(list)
    for f in all_fields:
        local_groups[(f.source, f.candidate_key)].append(f)

    # Step 2: compute a signature (emails, phones, name) per local group.
    signatures = []
    for key, fields in local_groups.items():
        emails = {_email_key(f.value) for f in fields if f.field == "emails" and isinstance(f.value, str)}
        phones = {_phone_key(f.value) for f in fields if f.field == "phones" and isinstance(f.value, str)}
        names = {f.value.strip().lower() for f in fields if f.field == "full_name" and isinstance(f.value, str)}
        signatures.append({"key": key, "fields": fields, "emails": emails, "phones": phones, "names": names})

    # Step 3: union-find merge across signatures that share an email, phone, or name.
    parent = list(range(len(signatures)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            a, b = signatures[i], signatures[j]
            if a["emails"] & b["emails"] and a["emails"]:
                union(i, j)
            elif a["phones"] & b["phones"] and a["phones"]:
                union(i, j)
            elif a["names"] & b["names"] and a["names"]:
                union(i, j)

    buckets: Dict[int, List[RawField]] = defaultdict(list)
    for i, sig in enumerate(signatures):
        buckets[find(i)].extend(sig["fields"])

    return list(buckets.values())


def _normalize_value(field: str, value: Any, context: Dict[str, Any]):
    if field == "phones":
        return normalize_phone(value, context.get("default_region"))
    if field == "emails":
        return normalize_email(value)
    if field in ("experience.start", "experience.end", "education.end_year"):
        return normalize_date(value)
    if field == "skills":
        return normalize_skill(value)
    if field == "full_name":
        return normalize_name(value)
    if field == "location.country":
        return normalize_country(value)
    if field in ("headline", "location.city", "location.region"):
        v = value.strip() if isinstance(value, str) else value
        return (v or None, 0.8 if v else 0.0, None if v else "empty")
    return (value, 0.7, None)


def _winner(values: List[Dict[str, Any]]) -> Dict[str, Any]:
    """values: list of {value, source, trust, norm_confidence}. Picks the
    highest (trust * norm_confidence); ties broken by cross-source agreement."""
    scored = []
    for v in values:
        score = v["trust"] * v["norm_confidence"]
        scored.append({**v, "score": score})
    scored.sort(key=lambda v: v["score"], reverse=True)
    best = scored[0]
    agreeing = [v for v in scored if v["value"] == best["value"]]
    if len(agreeing) > 1:
        best = dict(best)
        best["score"] = min(1.0, best["score"] + 0.1 * (len(agreeing) - 1))
        best["agreement_count"] = len(agreeing)
    return best


def _norm_text(s: Any) -> str:
    if not isinstance(s, str) or not s.strip():
        return ""
    return re.sub(r"\s+", " ", s.strip().lower()).rstrip(".,")


def _similar(a: str, b: str, threshold: float = 0.85) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _fuzzy_group_entries(raw_entries: List[Dict[str, Any]], match_fields: tuple) -> List[List[Dict[str, Any]]]:
    """Groups experience/education entries that likely describe the same
    real-world job/degree, even when wording differs slightly across
    sources (e.g. 'Beta Inc' vs 'Beta, Inc.', or a reworded summary).
    Two entries are grouped together when ALL of `match_fields` are
    near-identical (normalized exact match, or >=0.85 string similarity)
    between them. This is intentionally simple (no ML/embeddings) -- exact
    company/title or institution match catches the vast majority of
    cross-source duplicates without risking merging two genuinely
    different jobs/degrees together.
    """
    groups: List[List[Dict[str, Any]]] = []
    for item in raw_entries:
        entry = item["entry"]
        placed = False
        for group in groups:
            rep = group[0]["entry"]
            if all(_similar(_norm_text(entry.get(mf)), _norm_text(rep.get(mf))) for mf in match_fields):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return groups


def _merge_entry_group(group: List[Dict[str, Any]], list_field: str) -> Dict[str, Any]:
    """Given a group of near-duplicate experience/education entries from
    different sources, picks a per-sub-field winner (same trust*confidence
    logic as scalar fields) rather than keeping every source's full entry."""
    all_keys = set()
    for g in group:
        all_keys.update(g["entry"].keys())

    merged: Dict[str, Any] = {}
    for key in all_keys:
        candidates_for_key = [
            {"value": g["entry"].get(key), "score": g["score"]}
            for g in group if g["entry"].get(key) not in (None, "")
        ]
        if not candidates_for_key:
            merged[key] = None
            continue
        if key == "summary":
            # prefer the longest/most descriptive summary rather than a single "trust winner"
            best = max(candidates_for_key, key=lambda c: len(str(c["value"])))
        else:
            best = max(candidates_for_key, key=lambda c: c["score"])
        merged[key] = best["value"]
    return merged


def merge_candidate(fields: List[RawField]) -> Dict[str, Any]:
    """Normalizes + merges one candidate's RawFields into the canonical record."""
    # First pass: find a default_region hint (country) for phone normalization.
    country_hint = None
    for f in fields:
        if f.field == "location.country":
            val, conf, _ = normalize_country(f.value)
            if val:
                country_hint = val
                break
    context = {"default_region": country_hint}

    provenance: List[Dict[str, str]] = []
    candidate: Dict[str, Any] = {
        "candidate_id": str(uuid.uuid4()),
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": None,
        "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": [],
        "provenance": [],
        "overall_confidence": 0.0,
    }

    field_confidences: Dict[str, float] = {}

    # --- list-collected fields: emails / phones (union + dedupe) ---
    for fname, bucket_field in (("emails", "emails"), ("phones", "phones")):
        seen = {}
        for f in fields:
            if f.field != bucket_field:
                continue
            norm_val, norm_conf, err = _normalize_value(bucket_field, f.value, context)
            if not norm_val:
                continue
            trust = trust_for(bucket_field, f.source)
            key = norm_val
            entry = seen.setdefault(key, {"value": norm_val, "sources": [], "best_score": 0})
            entry["sources"].append((f.source, f.method))
            entry["best_score"] = max(entry["best_score"], trust * norm_conf)
        ordered = sorted(seen.values(), key=lambda e: e["best_score"], reverse=True)
        candidate[fname] = [e["value"] for e in ordered]
        for e in ordered:
            for source, method in e["sources"]:
                provenance.append({"field": fname, "value": e["value"], "source": source, "method": method})
        if ordered:
            field_confidences[fname] = max(e["best_score"] for e in ordered)

    # --- single-value fields: full_name, headline, years_experience ---
    for fname in ("full_name", "headline", "years_experience"):
        candidates_for_field = []
        for f in fields:
            if f.field != fname:
                continue
            norm_val, norm_conf, err = _normalize_value(fname, f.value, context)
            if norm_val in (None, ""):
                continue
            candidates_for_field.append({
                "value": norm_val, "source": f.source, "method": f.method,
                "trust": trust_for(fname, f.source), "norm_confidence": norm_conf,
            })
        if not candidates_for_field:
            continue
        best = _winner(candidates_for_field)
        candidate[fname] = best["value"]
        field_confidences[fname] = best["score"]
        provenance.append({"field": fname, "value": best["value"], "source": best["source"], "method": best["method"]})
    # --- location (assembled from sub-fields, winner-takes-all per sub-field) ---
    location: Dict[str, Any] = {}
    loc_scores = []
    for sub in ("city", "region", "country"):
        fname = f"location.{sub}"
        candidates_for_field = []
        for f in fields:
            if f.field != fname:
                continue
            norm_val, norm_conf, err = _normalize_value(fname, f.value, context)
            if not norm_val:
                continue
            candidates_for_field.append({
                "value": norm_val, "source": f.source, "method": f.method,
                "trust": trust_for("location", f.source), "norm_confidence": norm_conf,
            })
        if candidates_for_field:
            best = _winner(candidates_for_field)
            location[sub] = best["value"]
            loc_scores.append(best["score"])
            provenance.append({"field": fname, "value": best["value"], "source": best["source"], "method": best["method"]})
    if location:
        candidate["location"] = {"city": location.get("city"), "region": location.get("region"), "country": location.get("country")}
        field_confidences["location"] = sum(loc_scores) / len(loc_scores)

    # --- links (assembled, union for "other") ---
    links_out = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    link_scores = []
    for sub in ("linkedin", "github", "portfolio"):
        fname = f"links.{sub}"
        candidates_for_field = [
            {"value": f.value, "source": f.source, "method": f.method,
             "trust": trust_for("links", f.source), "norm_confidence": f.raw_confidence}
            for f in fields if f.field == fname and f.value
        ]
        if candidates_for_field:
            best = _winner(candidates_for_field)
            links_out[sub] = best["value"]
            link_scores.append(best["score"])
            provenance.append({"field": fname, "value": best["value"], "source": best["source"], "method": best["method"]})
    other_links = sorted({f.value for f in fields if f.field == "links.other" and f.value})
    links_out["other"] = other_links
    candidate["links"] = links_out
    if link_scores:
        field_confidences["links"] = sum(link_scores) / len(link_scores)

    # --- skills (union with per-skill confidence + sources, canonicalized) ---
    skill_map: Dict[str, Dict[str, Any]] = {}
    for f in fields:
        if f.field != "skills":
            continue
        norm_val, norm_conf, err = normalize_skill(f.value)
        if not norm_val:
            continue
        trust = trust_for("skills", f.source)
        entry = skill_map.setdefault(norm_val, {"name": norm_val, "sources": set(), "score": 0.0})
        entry["sources"].add(f.source)
        entry["score"] = max(entry["score"], trust * norm_conf)
    for name, entry in skill_map.items():
        if len(entry["sources"]) > 1:
            entry["score"] = min(1.0, entry["score"] + 0.1 * (len(entry["sources"]) - 1))
    skills_out = sorted(
        ({"name": e["name"], "confidence": round(e["score"], 2), "sources": sorted(e["sources"])} for e in skill_map.values()),
        key=lambda s: s["confidence"], reverse=True,
    )
    candidate["skills"] = skills_out
    for s in skills_out:
        for src in s["sources"]:
            provenance.append({"field": "skills", "value": s["name"], "source": src, "method": "merged"})
    if skills_out:
        field_confidences["skills"] = sum(s["confidence"] for s in skills_out) / len(skills_out)

    # --- experience / education: fuzzy dedupe + per-sub-field winner merge ---
    for list_field, date_keys, match_fields in (
        ("experience", ("start", "end"), ("company", "title")),
        ("education", ("end_year",), ("institution",)),
    ):
        raw_entries = []  # {entry: normalized dict, source, method, trust*conf}
        for f in fields:
            if f.field != list_field or not isinstance(f.value, dict):
                continue
            entry = dict(f.value)
            for dk in date_keys:
                if entry.get(dk):
                    norm_val, _, _ = normalize_date(entry[dk])
                    entry[dk] = norm_val
            trust = trust_for(list_field, f.source)
            raw_entries.append({
                "entry": entry, "source": f.source, "method": f.method,
                "score": trust * f.raw_confidence,
            })

        merged_groups = _fuzzy_group_entries(raw_entries, match_fields)

        final_entries = []
        scores = []
        for group in merged_groups:
            merged_entry = _merge_entry_group(group, list_field)
            final_entries.append(merged_entry)
            scores.append(max(g["score"] for g in group))
            entry_label = " / ".join(str(merged_entry.get(mf)) for mf in match_fields if merged_entry.get(mf))
            for g in group:
                provenance.append({"field": list_field, "value": entry_label, "source": g["source"], "method": g["method"]})

        candidate[list_field] = final_entries
        if scores:
            field_confidences[list_field] = sum(scores) / len(scores)

    candidate["provenance"] = provenance

    # --- overall_confidence: weighted average over fields actually present ---
    total_weight = 0.0
    weighted_sum = 0.0
    for fname, conf in field_confidences.items():
        w = FIELD_WEIGHTS.get(fname, 0.3)
        total_weight += w
        weighted_sum += w * conf
    candidate["overall_confidence"] = round(weighted_sum / total_weight, 3) if total_weight else 0.0

    return candidate


def merge_all(all_fields: List[RawField]) -> List[Dict[str, Any]]:
    groups = group_by_identity(all_fields)
    return [merge_candidate(g) for g in groups]
