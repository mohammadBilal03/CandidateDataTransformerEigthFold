import json
import os
import tempfile

from eightfold.pipeline import run_pipeline
from eightfold.project import project, MissingValueError


SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_inputs")


def test_pipeline_survives_malformed_and_missing_sources():
    """Garbage JSON and a nonexistent file must not crash the run; they
    should simply be skipped with a warning."""
    result = run_pipeline([
        os.path.join(SAMPLE_DIR, "garbage.json"),
        os.path.join(SAMPLE_DIR, "does_not_exist.csv"),
        os.path.join(SAMPLE_DIR, "recruiter.csv"),
    ])
    assert result["stats"]["inputs_skipped"] >= 1
    assert any("garbage" in w or "does_not_exist" in w for w in result["warnings"])
    assert len(result["profiles"]) > 0  # the good CSV source still produced candidates


def test_pipeline_runs_on_structured_plus_unstructured_minimum():
    """Covers >=1 structured (CSV) + >=1 unstructured (notes) source end to end."""
    result = run_pipeline([
        os.path.join(SAMPLE_DIR, "recruiter.csv"),
        os.path.join(SAMPLE_DIR, "notes_janedoe.txt"),
    ])
    assert result["stats"]["inputs_processed"] == 2
    assert len(result["profiles"]) >= 1


def test_empty_resume_does_not_crash():
    result = run_pipeline([os.path.join(SAMPLE_DIR, "empty_resume.pdf")])
    assert result["profiles"] == []
    assert any("no usable data" in w for w in result["warnings"])


def test_config_on_missing_error_flags_record_without_failing_run():
    canonical = {"candidate_id": "x1", "emails": [], "full_name": None, "overall_confidence": 0.0, "provenance": []}
    config = {"fields": [{"path": "primary_email", "from": "emails[0]", "required": True}], "on_missing": "error"}
    try:
        project(canonical, config)
        assert False, "expected MissingValueError"
    except MissingValueError:
        pass


def test_config_on_missing_omit_drops_key():
    canonical = {"candidate_id": "x1", "emails": [], "full_name": "Jane", "overall_confidence": 0.5, "provenance": []}
    config = {"fields": [
        {"path": "full_name"},
        {"path": "primary_email", "from": "emails[0]"},
    ], "on_missing": "omit"}
    out = project(canonical, config)
    assert out["full_name"] == "Jane"
    assert "primary_email" not in out


def test_config_on_missing_null_fills_null():
    canonical = {"candidate_id": "x1", "emails": [], "full_name": "Jane", "overall_confidence": 0.5, "provenance": []}
    config = {"fields": [{"path": "primary_email", "from": "emails[0]"}], "on_missing": "null"}
    out = project(canonical, config)
    assert out["primary_email"] is None


def test_full_cli_run_against_sample_inputs_produces_valid_json(tmp_path=None):
    out_path = os.path.join(tempfile.mkdtemp(), "out.json")
    result = run_pipeline([
        os.path.join(SAMPLE_DIR, "recruiter.csv"),
        os.path.join(SAMPLE_DIR, "ats.json"),
        os.path.join(SAMPLE_DIR, "linkedin_janedoe.json"),
        os.path.join(SAMPLE_DIR, "resume_janedoe.pdf"),
        os.path.join(SAMPLE_DIR, "notes_janedoe.txt"),
    ])
    with open(out_path, "w") as f:
        json.dump(result["profiles"], f)
    with open(out_path) as f:
        reloaded = json.load(f)
    assert isinstance(reloaded, list)
    jane = next((c for c in reloaded if c.get("full_name") == "Jane Doe"), None)
    assert jane is not None
    assert "jane.doe@example.com" in jane["emails"]
    assert jane["phones"] == ["+14155550142"]
    assert jane["overall_confidence"] > 0
