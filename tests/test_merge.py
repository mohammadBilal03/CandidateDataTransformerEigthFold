from eightfold.models import RawField
from eightfold.merge import group_by_identity, merge_candidate, merge_all


def test_group_by_identity_links_across_sources_via_email():
    fields = [
        RawField("row1", "full_name", "Jane Doe", "recruiter_csv", "csv_column:name", 0.95),
        RawField("row1", "emails", "jane@x.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("p1", "emails", "jane@x.com", "linkedin", "export:email", 0.8),
        RawField("p1", "headline", "Engineer", "linkedin", "export:headline", 0.8),
        RawField("other", "emails", "bob@x.com", "recruiter_csv", "csv_column:email", 0.95),
    ]
    groups = group_by_identity(fields)
    assert len(groups) == 2
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 4]


def test_merge_picks_higher_trust_source_for_conflicting_name():
    fields = [
        RawField("k", "full_name", "Jane Doe", "recruiter_csv", "csv_column:name", 0.95),
        RawField("k", "full_name", "J. D.", "notes", "heuristic:first_sentence", 0.5),
        RawField("k", "emails", "jane@x.com", "recruiter_csv", "csv_column:email", 0.95),
    ]
    record = merge_candidate(fields)
    assert record["full_name"] == "Jane Doe"


def test_merge_unions_and_dedupes_emails():
    fields = [
        RawField("k", "emails", "Jane@X.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("k", "emails", "jane@x.com", "linkedin", "export:email", 0.8),
        RawField("k", "emails", "alt@x.com", "notes", "regex:email", 0.5),
    ]
    record = merge_candidate(fields)
    assert sorted(record["emails"]) == ["alt@x.com", "jane@x.com"]


def test_merge_handles_empty_input_gracefully():
    record = merge_candidate([])
    assert record["emails"] == []
    assert record["overall_confidence"] == 0.0


def test_merge_skill_confidence_boosted_by_corroboration():
    fields = [
        RawField("k", "skills", "Python", "github", "api:repo_language", 0.6),
        RawField("k", "skills", "python", "resume", "keyword_match:skills", 0.5),
    ]
    record = merge_candidate(fields)
    python_skill = next(s for s in record["skills"] if s["name"] == "python")
    assert set(python_skill["sources"]) == {"github", "resume"}
    assert python_skill["confidence"] > 0


def test_merge_all_end_to_end_two_candidates():
    fields = [
        RawField("a", "emails", "a@x.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("a", "full_name", "Alice", "recruiter_csv", "csv_column:name", 0.95),
        RawField("b", "emails", "b@x.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("b", "full_name", "Bob", "recruiter_csv", "csv_column:name", 0.95),
    ]
    records = merge_all(fields)
    names = sorted(r["full_name"] for r in records)
    assert names == ["Alice", "Bob"]


def test_merge_fuzzy_dedupes_same_job_from_two_sources():
    """Two sources describing the same job with slightly different wording
    should collapse into ONE experience entry, not two."""
    fields = [
        RawField("k", "emails", "jane@x.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("k", "experience", {
            "company": "Acme Corp", "title": "Senior Backend Engineer",
            "start": "2021-03", "end": "present", "summary": "Leads payments platform team.",
        }, "ats_json", "ats_key:workhistory[]", 0.85),
        RawField("k", "experience", {
            "company": "Acme Corp", "title": "Senior Backend Engineer",
            "start": "March 2021", "end": "present", "summary": "Leads the payments platform team in depth.",
        }, "linkedin", "export:experience[]", 0.85),
    ]
    record = merge_candidate(fields)
    assert len(record["experience"]) == 1
    assert record["experience"][0]["company"] == "Acme Corp"
    # the longer, more descriptive summary should win
    assert "in depth" in record["experience"][0]["summary"]


def test_merge_does_not_collapse_genuinely_different_jobs():
    """Two different roles at two different companies must stay separate."""
    fields = [
        RawField("k", "emails", "jane@x.com", "recruiter_csv", "csv_column:email", 0.95),
        RawField("k", "experience", {"company": "Acme Corp", "title": "Senior Backend Engineer",
                                      "start": "2021-03", "end": "present"}, "ats_json", "m", 0.85),
        RawField("k", "experience", {"company": "Beta Inc", "title": "Backend Engineer",
                                      "start": "2018-01", "end": "2021-02"}, "linkedin", "m", 0.85),
    ]
    record = merge_candidate(fields)
    assert len(record["experience"]) == 2
