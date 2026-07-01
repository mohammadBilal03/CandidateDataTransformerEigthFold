# Eightfold Candidate Profile Normalization Engine

Turns messy, multi-source candidate data into one clean, canonical, provenance-tracked
profile per candidate, with a runtime-configurable projection layer for custom output
shapes. Implements the design in `<YourFullName>_<YourEmail>_Eightfold.pdf`.

## Quick start

```bash
pip install -r requirements.txt

# Default schema, all sample sources
python3 -m eightfold.cli \
  --input sample_inputs/recruiter.csv \
  --input sample_inputs/ats.json \
  --input sample_inputs/linkedin_janedoe.json \
  --input sample_inputs/resume_janedoe.pdf \
  --input sample_inputs/notes_janedoe.txt \
  --input https://github.com/octocat \
  --out sample_outputs/default_schema_output.json

# Same inputs, custom runtime config (subset/rename/normalize fields)
python3 -m eightfold.cli \
  --input sample_inputs/recruiter.csv \
  --input sample_inputs/ats.json \
  --input sample_inputs/linkedin_janedoe.json \
  --config sample_inputs/config_example.json \
  --out sample_outputs/custom_config_output.json
```

Output is the projected JSON array (one object per resolved candidate); run stats and
per-record validation warnings print to stderr unless `--quiet` is passed.

Run tests: `python3 -m pytest tests/ -v` (27 tests covering normalizers, merge/identity
resolution, and pipeline edge cases).

## Pipeline

`detect → extract → normalize → merge → confidence → project → validate`, matching the
design doc. Each stage is an independent, testable module under `eightfold/`:

- `adapters/` — one per source type (`csv_adapter`, `ats_json_adapter`, `github_adapter`,
  `linkedin_adapter`, `resume_adapter`, `notes_adapter`), each producing a list of
  `RawField`s (`models.py`). `adapters/base.py` does source-type detection by
  extension/content sniff.
- `normalize.py` — pure functions per data type (phone → E.164, date → YYYY-MM,
  skill → canonical taxonomy, country → ISO-3166 alpha-2, email, name).
- `trust.py` — static, explainable per-source/per-field trust weights used as the merge
  conflict-resolution policy.
- `merge.py` — identity resolution (`group_by_identity`, matching on normalized
  email → phone → fuzzy name) and per-field winner selection + confidence scoring
  (`merge_candidate`). Each `provenance` entry is `{field, value, source, method}` —
  `field` uses the sub-path where relevant (`location.city`, `links.github`) and
  `value` identifies exactly which contribution this is (a skill name, an
  `"Company / Title"` label for experience), so two entries with the same source
  are still distinguishable.
- `project.py` — runtime-config projection layer; never mutates the canonical record.
- `validate.py` — validates canonical or projected output against the default schema
  or the config's declared field types; degrades to warnings rather than raising.
- `pipeline.py` — orchestrates the above; `cli.py` is the thin CLI wrapper.

## Sources covered (2 structured + 4 unstructured)

| Source | Type | Adapter |
|---|---|---|
| Recruiter CSV | structured | `csv_adapter.py` |
| ATS JSON (non-matching field names) | structured | `ats_json_adapter.py` |
| GitHub profile | unstructured (live public API) | `github_adapter.py` |
| LinkedIn profile | unstructured (see assumption below) | `linkedin_adapter.py` |
| Resume PDF/DOCX | unstructured | `resume_adapter.py` |
| Recruiter notes .txt | unstructured | `notes_adapter.py` |

**LinkedIn assumption:** LinkedIn has no public, unauthenticated API and scraping
linkedin.com isn't reachable from this sandbox / violates ToS, so `linkedin_adapter.py`
consumes a **local JSON export** of an already-fetched profile (shape documented in the
adapter's docstring) rather than live-scraping a URL. A bare `https://linkedin.com/...`
URL with no matching export degrades to zero fields, consistent with "missing source
must not crash."

**GitHub** genuinely calls the live public REST API (`api.github.com`) for profile +
repo languages — see the example `https://github.com/octocat` input above.

## Runtime config / custom output

See `sample_inputs/config_example.json` for the exact example from the problem
statement (rename via `from`, `E164`/`canonical` normalization, `include_confidence`,
`on_missing: "null"`). `on_missing` also supports `"omit"` (drop the key) and `"error"`
(fail validation for that record only — the rest of the batch still completes).

## Tests / edge cases covered

`tests/test_pipeline_edge_cases.py` specifically exercises:
- a malformed/unparseable JSON source (skipped with a warning, run continues)
- a missing/nonexistent input file (skipped, run continues)
- an empty/unreadable PDF (zero fields, no crash)
- `on_missing` = error / omit / null behavior in the projection layer
- a full run across structured + unstructured sources producing a valid, schema-matching
  merged profile (gold-profile-style assertion on the merged Jane Doe record)

`tests/test_merge.py` covers identity linking across sources via email, conflict
resolution favoring higher-trust sources, email dedupe/union, and confidence
corroboration boosts.

## Assumptions & deliberately descoped (time-boxed)

- Identity matching is deterministic (email → phone → fuzzy name), not ML-based.
- Experience/education dedupe groups near-duplicate entries across sources by
  normalized company+title (experience) or institution (education), using
  string-similarity matching (`difflib`, ≥0.85 ratio) rather than exact match,
  then merges each group into one entry by picking the best value per
  sub-field (trust-weighted, except `summary` which prefers the most
  descriptive text). This is intentionally simple normalized/fuzzy matching,
  not embeddings or ML — exact-enough for company/title/institution, where a
  false merge (collapsing two genuinely different jobs) would be worse than
  occasionally keeping two entries separate.
- No retry/backoff beyond a single best-effort attempt for the GitHub API call.
- No multi-language resume parsing (English-oriented regex heuristics).
- CLI only; no UI, per the prompt's lower-priority note on I/O surface.
- Resume/notes field extraction is regex/heuristic-based, not NLP/LLM-based, to stay
  deterministic and dependency-light.

## Demo

Run the two commands under **Quick start** — they reproduce `sample_outputs/`.
