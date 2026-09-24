# onboarding-rag

Version-aware retrieval for enterprise onboarding: M.Tech dissertation project.

## Research problem

Enterprise policy documents change over time, but older versions often stay
in the knowledge base alongside the new ones. A standard retrieval pipeline
ranks passages by relevance alone. It can return a superseded policy, or the
wrong one of two versions that are both valid for different groups of
employees (for example, by join date or office location). This project asks
how retrieval can take document versions and applicability conditions into
account, so that an employee gets the policy that actually applies to them.

## Repository layout

```
corpus/                  synthetic policy documents + manifest.csv
scripts/validate_corpus.py   consistency checks for the corpus
test_setup.py            smoke test for the retrieval libraries
requirements.txt         Python dependencies
```

## The corpus

`corpus/` holds 30 synthetic Markdown policy documents. They form 15 pairs,
each with a v1 and a v2 (`<base>-v1.md` / `<base>-v2.md`), across four
departments: HR, IT, Facilities and Finance. The two versions in a pair are
nearly identical text, except for one fact that differs (for example, a leave
carry-forward cap of 12 vs 5 days). The pairs are one of two kinds:

- **Full replacement.** v2 replaces v1 for everyone (`applies_if: []`).
- **Conditional split.** v1 still governs one group and v2 governs another,
  based on join date, department or location.

### Frontmatter schema

Each document starts with a YAML frontmatter block:

| Field | Type | Meaning |
|---|---|---|
| `doc_id` | string | Unique ID. Must match the filename, e.g. `hr-leave-policy-v1`. |
| `title` | string | Policy title, shared by both versions. |
| `version` | int | `1` or `2`. Must match the `-vN` suffix of `doc_id`. |
| `effective_date` | date | Date this version took effect. |
| `status` | string | `current` or `superseded`. |
| `superseded_by` | string or null | `doc_id` of the newer version. Set if and only if `status` is `superseded`. |
| `applies_if` | list | Conditions for who this version governs. Empty means no condition. Each item is `{field, op, value}`. `field` is one of `join_date`, `department`, `employment_type` or `location`. `op` is one of `== != < <= > >=`. |
| `conflicts_with` | list | IDs of documents this one conflicts with. Currently empty in every document. |
| `sensitivity` | string | Access classification. Currently `internal` for every document. |
| `department_scope` | list | Departments the policy is aimed at, e.g. `[all]` or `[Engineering]`. |
| `owner` | string | Owning team, e.g. `HR - People Operations`. |

Example:

```yaml
doc_id: hr-leave-policy-v1
title: Annual Leave Policy
version: 1
effective_date: 2023-01-01
status: superseded
superseded_by: hr-leave-policy-v2
applies_if:
  - {field: join_date, op: "<", value: 2025-04-01}
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: HR - People Operations
```

### manifest.csv

`corpus/manifest.csv` has one row per document. It records the document's
metadata, the `differing_fact` between the two versions, the `value` of that
fact in this version, and a plain-English `governs` description of who the
version applies to. The `value` column must be an exact substring of the
document body, so it can be used as a ground-truth answer string.

## Validating the corpus

`scripts/validate_corpus.py` checks the following:

1. **Frontmatter:** every required field is present and has the right type.
   `doc_id` matches the filename, `version` matches the suffix, and `status`
   is consistent with `superseded_by`. `applies_if` conditions use known
   fields and operators, and `join_date` values are real dates.
2. **Pairing:** every `superseded_by` target exists, every v1 has a v2, each
   v2 is superseded by exactly one v1, and the two share a base name.
3. **Pair body diffs:** v1 and v2 bodies differ by at most 3 lines. The check
   ignores the `(v1)`/`(v2)` heading tag and v2 lines announcing that it
   replaces v1.
4. **Effective dates:** no v2 has an `effective_date` after 2026-09-01.
5. **Manifest:** every document appears in the manifest and every manifest
   row has a document. Each `value` must be a verbatim substring of its
   document's body and must not occur only inside a larger token (so
   `5 days` does not match inside `15 days`).

It also prints body word counts for each document (informational only).

Run it from the repository root:

```
python scripts/validate_corpus.py
```

It prints `FAIL` lines for each problem and exits with code 1 if any check
fails, or 0 if everything passes.

## Setup

The project has been used with Python 3.13.

```powershell
python -m venv venv
venv\Scripts\activate          # Windows (PowerShell)
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

`requirements.txt` installs rank-bm25, sentence-transformers, chromadb,
pandas, numpy, scikit-learn and pyyaml. The validator needs only pyyaml.

To check that the retrieval libraries work:

```
python test_setup.py
```

This scores a few toy sentences with BM25 and with the `all-MiniLM-L6-v2`
sentence-transformers model. The model (~90 MB) downloads on first run.

## Status

Early stage. What exists so far:

- The 30-document versioned corpus, its manifest, and a validator that
  passes on the current corpus.
- A smoke test confirming that BM25 and sentence-transformers are installed
  and working.

Not built yet: indexing the corpus, a retrieval pipeline (baseline or
version-aware), evaluation queries, and evaluation results. chromadb, pandas
and scikit-learn are installed but not used by any code yet.
