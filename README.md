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
corpus/                      synthetic documents + manifest.csv
data/user_profiles.json      test employee profiles
scripts/validate_corpus.py   consistency checks for the corpus
scripts/check_conflicts.py   checks standalone docs do not restate policy values
test_setup.py                smoke test for the retrieval libraries
requirements.txt             Python dependencies
```

## The corpus

`corpus/` holds 148 synthetic Markdown documents across six departments:
HR (37), IT (34), Finance (23), Facilities (21), Engineering (17) and
Legal (16). Body lengths range from 85 to 1074 words (median about 300).
Each document falls into exactly one of five categories:

| Category | Count | What it is | What it tests |
|---|---|---|---|
| Versioned | 30 | 15 v1/v2 policy pairs (`doc_kind: policy_version`) | Supersession and applicability conditions |
| Ordinary | 80 | Standalone how-tos, FAQs, checklists and wikis that point to policies instead of restating them | Realistic distractors |
| Conflicting | 12 | Standalone documents that restate a superseded policy value | Declared conflicts (`conflicts_with`) |
| Restricted | 18 | Standalone documents with `sensitivity: restricted` or `confidential` | Access control |
| Stale | 8 | Standalone documents from 2019–2022 that describe things that no longer exist | Freshness |

### Versioned pairs

Each pair has a v1 and a v2 (`<base>-v1.md` / `<base>-v2.md`). The two
versions are nearly identical text, except for one fact that differs (for
example, a leave carry-forward cap of 12 vs 5 days). The pairs are one of
two kinds:

- **Full replacement.** v2 replaces v1 for everyone (`applies_if: []`).
- **Conditional split.** v1 still governs one group and v2 governs another,
  based on join date, department or location.

### Conflicting documents

A conflicting document is a standalone page, such as a team FAQ or a crib
sheet, that still quotes the v1 value of a versioned fact. It lists the
current policy version in `conflicts_with`, and that version lists it back.
Every other standalone document must refer to the policy rather than quote
its value; `scripts/check_conflicts.py` enforces this.

### Stale documents

A stale document has `status: current`, no `superseded_by` and no
`conflicts_with`, but its content has obviously moved on: an old office
address, a discontinued file-sharing tool, remote desktop access from before
the VPN, a retired expense system, a 2021 org chart, printers set up by IP
address, a legacy ticketing system and a deprecated build server. No newer
version exists for supersession to find, so these test a freshness signal
(for example, `effective_date`), which is separate from supersession. They
are flagged `stale=true` in the manifest.

### Frontmatter schema

Each document starts with a YAML frontmatter block:

| Field | Type | Meaning |
|---|---|---|
| `doc_id` | string | Unique ID. Must match the filename, e.g. `hr-leave-policy-v1`. |
| `title` | string | Policy title, shared by both versions. |
| `doc_kind` | string | `policy_version` for a document that is one half of a v1/v2 pair, `standalone` for everything else. A standalone document must have `version: null`, `status: current`, `superseded_by: null`, and no `-vN` suffix in its `doc_id`. |
| `version` | int or null | For `policy_version`: `1` or `2`, matching the `-vN` suffix of `doc_id`. For `standalone`: `null`. |
| `effective_date` | date | Date this version took effect. |
| `status` | string | `current` or `superseded`. |
| `superseded_by` | string or null | `doc_id` of the newer version. Set if and only if `status` is `superseded`. |
| `applies_if` | list | Conditions for who this version governs. Empty means no condition. Each item is `{field, op, value}`. `field` is one of `join_date`, `department`, `employment_type` or `location`. `op` is one of `== != < <= > >=`. |
| `conflicts_with` | list | IDs of documents this one conflicts with. Set in both directions: a standalone document that restates a superseded value lists the current version, and that version lists it back. Empty otherwise. |
| `sensitivity` | string | Access classification: `internal`, `restricted` or `confidential`. |
| `department_scope` | list | Departments the policy is aimed at, e.g. `[all]` or `[Engineering]`. |
| `owner` | string | Owning team, e.g. `HR - People Operations`. |

Example:

```yaml
doc_id: hr-leave-policy-v1
title: Annual Leave Policy
doc_kind: policy_version
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

`corpus/manifest.csv` has one row per document, with these columns:

| Column | Meaning |
|---|---|
| `doc_id`, `title`, `version`, `status`, `superseded_by`, `sensitivity` | Copied from the frontmatter. |
| `department` | Owning department. |
| `applies_if` | The frontmatter conditions in plain form, e.g. `join_date < 2025-04-01`, or `[]`. |
| `differing_fact` | Versioned and conflicting documents: the fact that differs between v1 and v2. Empty otherwise. |
| `value` | That fact's value as written in this document. It must be an exact substring of the document body, so it can be used as a ground-truth answer string. |
| `governs` | Versioned documents: plain-English description of who this version applies to. |
| `correct_doc_id` | Conflicting documents: the current policy version that holds the correct value. |
| `stale` | `true` for the 8 stale documents, `false` for everything else. |

### User profiles

`data/user_profiles.json` holds 6 test employees, each with `user_id`,
`name`, `department`, `grade`, `location`, `employment_type` and
`join_date`. Together they cover both sides of the conditional-split pairs,
so the same question should resolve to different policy versions for
different users.

## Validating the corpus

`scripts/validate_corpus.py` checks the following:

1. **Frontmatter:** every required field is present and has the right type.
   `doc_id` matches the filename, `version` matches the suffix, and `status`
   is consistent with `superseded_by`. `doc_kind` is `policy_version` or
   `standalone`, and standalone documents follow the rules in the schema
   table above. `applies_if` conditions use known
   fields and operators, and `join_date` values are real dates.
2. **Pairing** (`policy_version` documents only): every `superseded_by`
   target exists and is a `policy_version` document, every v1 has a v2, each
   v2 is superseded by exactly one v1, and the two share a base name.
3. **Pair body diffs** (`policy_version` pairs only): v1 and v2 bodies
   differ by at most 3 lines. The check ignores the `(v1)`/`(v2)` heading tag and v2 lines announcing that it
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

`scripts/check_conflicts.py` scans every standalone document for the values
of the versioned facts, written as digits or words (e.g. `30 minutes` or
`thirty-minute`). It flags a sentence only if the sentence, or the heading
above it, also has a topic keyword for that fact. Documents with a non-empty
`conflicts_with` are skipped, because their conflict is intentional and
declared. It exits with code 1 if it finds a match:

```
python scripts/check_conflicts.py
```

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

- The 148-document corpus (versioned, ordinary, conflicting, restricted and
  stale), its manifest, and 6 user profiles.
- A validator and a conflict checker, both passing on the current corpus.
- A smoke test confirming that BM25 and sentence-transformers are installed
  and working.

Not built yet: indexing the corpus, a retrieval pipeline (baseline or
version-aware), evaluation queries, and evaluation results. chromadb, pandas
and scikit-learn are installed but not used by any code yet.
