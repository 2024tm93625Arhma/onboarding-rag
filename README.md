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
data/chunks.jsonl            section-level chunks (written by src/ingest.py)
data/supersession.json       supersession lookup (written by src/ingest.py)
data/chroma/                 persistent vector index (written by src/index_chunks.py; not in git)
src/ingest.py                chunks the corpus and builds the supersession lookup
src/index_chunks.py          embeds chunks and builds the ChromaDB collection
src/provenance.py            applicability, access scope and policy-family helpers
src/retrievers.py            five baselines, scoped_search and provenance_rank
src/evaluate.py              runs every retriever over the query set; writes data/results/
data/queries.csv             108 annotated evaluation queries
data/query_split.csv         dev/test split of the queries (written by scripts/make_split.py)
data/results/                evaluation output (baselines, method, per-category, answer modes)
tests/test_leakage.py        scoped_search never returns a leakage probe's restricted doc
tests/test_conflicts.py      provenance_rank keeps contradicting pages out of the top 5
scripts/smoke_test_index.py  sample query against the index, with and without a status filter
scripts/validate_corpus.py   consistency checks for the corpus
scripts/check_conflicts.py   checks standalone docs do not restate policy values
scripts/check_chunks.py      checks chunks against the manifest; fills gold_chunk_id
scripts/make_split.py        stratified dev/test split of the query set
scripts/calibrate_relevance_floor.py  fits RELEVANCE_FLOOR on the dev split
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
| `gold_chunk_id` | Rows with a `value`: the `chunk_id` of the one chunk of this document whose `chunk_body` contains the value. Empty otherwise. Generated, not hand-edited: `python scripts/check_chunks.py --write-gold` fills it in, and a plain run fails if it no longer matches the current chunking. |

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

## Evaluation design decisions

**Correctness is scored by chunk identity, not by string match.** A retrieved
result counts as correct only if it is the expected gold chunk
(`gold_chunk_id`), or, for document-level metrics, if its `parent_doc_id` is
the expected document. Finding the `value` string somewhere in the retrieved
text does **not** count.

Why: many values are ambiguous across the corpus. Conflicting documents
repeat v1 values on purpose, and short values such as `3 days`, `7 days` or
`INR 1,500` appear in unrelated documents (`scripts/check_chunks.py` lists
these overlaps). A string-match scorer would give credit for retrieving a
superseded version, a conflicting crib sheet or an unrelated page that
happens to contain the same string. Those are exactly the failures this
project sets out to measure.

The `value` column is still used to check the ground truth itself (it must
appear verbatim in its document, and in exactly one of its chunks). It is
not used as the correctness criterion when scoring retrieval.

**Neither similarity nor status can pick between the versions of a
conditional pair.** On the query "how many leave days can I carry forward",
the current and superseded versions of the Annual Leave Policy were
retrieved at cosine distances of 0.197 and 0.200, a separation of about
0.003. The two chunks are word-for-word identical apart from the version tag
and the carry-forward limit (5 days in v2, 12 in v1), so semantic similarity
gives no reliable basis for choosing between them. Filtering on
`status = current` removes the superseded version, but then employees who
joined before 1 April 2025 get the wrong limit, because v1 still governs
them. The right chunk has to be chosen by checking each chunk's `applies_if`
conditions against the user's profile, not by similarity or status.
(Reproduce with `python scripts/smoke_test_index.py`.)

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

## Results

All numbers below come from `data/results/` and are reproduced with:

```
python src/evaluate.py
```

The script runs every retriever over the 108 queries in `data/queries.csv`
(version_conflict 20, user_dependent 19, cross_doc_conflict 12, ordinary 25,
stale 8, leakage_probe 12, unanswerable 12), with each query answered for
its `asking_user_id`. Recall@5 and MRR are scored on the 84 queries that have
a gold chunk. The 24 leakage-probe and unanswerable queries have no gold
chunk, so they are counted only in the two validity rates.

- **IER (invalid-evidence rate):** share of queries whose top-1 chunk is
  invalid for the asking user. A chunk is invalid if its `applies_if` does
  not hold for the user, if it comes from the query's `must_not_use_doc_id`,
  or if it is out of the user's scope.
- **SVR (scope-violation rate):** share of queries with any out-of-scope
  chunk in the top 5.

### Overall

| Retriever | Recall@5 | MRR | IER | SVR |
|---|---|---|---|---|
| BM25 | 0.750 | 0.486 | 21.3% | 21.3% |
| Dense | **0.929** | **0.743** | 30.6% | 23.1% |
| Hybrid (RRF) | 0.821 | 0.610 | 26.9% | 22.2% |
| Cross-encoder rerank | 0.869 | 0.697 | 33.3% | 25.9% |
| Recency prior | 0.762 | 0.661 | 21.3% | 22.2% |
| Scoped search (hybrid + scope filter) | 0.786 | 0.580 | 13.0% | **0.0%** |
| **Provenance rank (proposed)** | 0.786 | 0.693 | **0.0%** | **0.0%** |

The first five rows are baselines. None of them reads `applies_if`, `status`
or the user profile. Scoped search and provenance rank both use hybrid as
their base retriever.

### Findings

**Retrieval quality and evidence validity move in opposite directions.**
Dense has the best Recall@5 (0.929) and the reranker the second best
(0.869), yet they have the two worst IERs (30.6% and 33.3%). BM25 has the
worst recall (0.750) and the lowest IER (21.3%, tied with the recency prior).
The stronger retrievers are better at finding the right policy family, and
that makes them equally good at surfacing the wrong version of it.

**"Prefer the newest" fails on grandfathered employees.** The recency prior
reaches IER 0% on version_conflict queries, where v2 replaces v1 for
everyone. On user_dependent queries its Recall@5 drops to 0.526, the worst of
any retriever in any category. For those queries, v1 still governs part of
the workforce, for example employees who joined before a cut-off date, and
the recency prior pushes v1 down for them.

**BM25 is systematically biased toward the superseded version.** The two
versions of a pair are near-identical text, so BM25 often scores them
exactly the same. On the smoke-test query "how many leave days can I carry
forward", both leave-policy chunks score 22.881. `bm25_search` sorts by score
with a stable sort, so tied chunks keep their order in `data/chunks.jsonl`,
and there v1 comes before v2. Across the 39 version_conflict and
user_dependent queries, both versions appeared in BM25's top 100 for 38.
They tied exactly in 31 of those, and v1 ranked above v2 in all 31.

**Dense finds the family but not the version.** On user_dependent queries,
dense reaches Recall@5 1.000 with IER 42.1%. It retrieves the right policy
family every time, but for nearly half the users its top-1 chunk is the
version that does not apply to them. The reranker has the same IER on this
category, with lower recall.

**Every baseline leaks restricted content.** On the 12 leakage probes, all
five baselines put a chunk the user may not see in the top 5 (SVR 100%).
The scope filter alone brings this to 0%. `python tests/test_leakage.py`
checks it per query.

**The proposed method has no invalid or out-of-scope evidence.** Provenance
rank reaches IER 0% and SVR 0% in every query category. Against hybrid, its
base retriever, that costs 3.6 points of Recall@5 (0.786 vs 0.821). The
scope filter accounts for all of that loss: scoped search has the same
Recall@5. Authority, freshness and the conflict penalty then raise MRR from
0.580 to 0.693.

**Freshness works against stale queries.** The freshness term F(d,t) decays
with document age. For the 8 stale queries, though, the gold answer *is* the
old document, which has no replacement. MRR on stale queries falls from
0.875 (scoped search) to 0.750 (provenance rank). In q065 and q070 the stale
gold document drops from rank 1 to rank 2 behind a newer, less relevant
page, and setting GAMMA to 0 restores rank 1. For these queries the
expected behaviour is `answer_conditionally`, meaning answer from the old
page and flag its age, not to demote it.

**The conflict penalty removes every contradicting page from the top 5.**
All 12 declared conflicts pair a current policy version with a standalone
page that restates its superseded value. Authority cannot separate them
(both get A = 1.0), so the lower side is chosen by the precedence key
(A, is policy_version, effective_date): the formal policy beats the
derivative page, then the later date wins. Without the penalty (DELTA = 0)
the contradicting page is in provenance rank's top 5 for 8 of the 12
cross_doc_conflict queries. With DELTA = 0.4 it is in none of them
(`python tests/test_conflicts.py`). The effect on ranking metrics is small,
because the policy already ranked first: cross_doc_conflict MRR goes from
0.855 to 0.858, and overall MRR from 0.691 to 0.693.

### Answer modes

`provenance_answer` takes `provenance_rank`'s top 5 and applies these checks
in order:

1. **Relevance floor → `abstain`.** The cross-encoder
   (`ms-marco-MiniLM-L-6-v2`) scores (query, top-1 chunk). If the logit is
   below `RELEVANCE_FLOOR` = 2.1444, the mode is `abstain`, whatever the
   conflict checks would say. An empty scoped pool also gives `abstain`.
2. **Unresolved conflict → `abstain`.** A declared-conflict pair of comparable
   authority (|ΔA| ≤ 0.1) is still in the top 5, and the top-1 is its lower-
   precedence side, or the pair cannot be ordered.
3. **`answer_conditionally`.** Such a pair is still there but the top-1 is
   its winning side, or the top-1 chunk's freshness is below
   `FRESHNESS_FLOOR` = e⁻¹ ≈ 0.368 (its effective_date is more than
   `FRESHNESS_SCALE` = 5 years before the reference date).
4. Otherwise, **`answer`**.

Without the two floors (checks 2 to 4 only), every one of the 108 queries
got `answer`: false-answer rate 100% (24/24), false-abstention rate 0%
(0/76), mode accuracy 70.4%. The conflict signal could not separate the
modes, for two reasons:

- **The penalty resolves every conflict before the mode is chosen.** With
  DELTA = 0, the same rule returns `answer_conditionally` for 18 queries,
  17 of which are expected to be `answer`. At DELTA = 0.4 every penalised
  page leaves the top 5, so no unresolved pair is left. On this corpus, the
  precedence key always orders a declared pair, so `abstain` cannot come from
  a conflict at all.
- **Abstain queries fail through missing evidence, not conflicting
  evidence.** Leakage probes ask for documents the scope filter has already
  removed, and unanswerable queries have no supporting document. In both
  cases the top 5 holds other in-scope pages that don't conflict, so the
  mode is `answer`. The stale queries likewise need an age signal, not a
  conflict signal.

The two floors provide those signals: relevance for evidence sufficiency,
and freshness for age.

**Why a cross-encoder rather than `rel`.** `rel` is min-max normalised
within the scoped pool, so the top-1 is always close to 1.0, even when the
pool is all off-topic. The raw hybrid RRF score is an absolute value, but
it depends only on rank, and the top-1 nearly always scores close to
2/61 ≈ 0.033. Over the 100 answer and abstain queries, the AUC for
separating answer from abstain is 0.77 for raw RRF and 0.90 for the
cross-encoder logit on the top-1.

**How the threshold was chosen.** `data/query_split.csv` splits the queries
into dev (55) and test (53) halves, stratified by category, with a fixed
seed (`scripts/make_split.py`). Before this there was no dev split, so a
threshold tuned to separate "the 24 abstain from the 76 answer queries"
would have been tuned on the full evaluation set.
`scripts/calibrate_relevance_floor.py` scores only the 12 abstain and 39
answer dev queries. It tries the midpoint between each pair of adjacent
scores and keeps the one with the highest balanced accuracy,
½·(abstain recall + answer recall). Balanced accuracy is used because the
classes are imbalanced. Ties go to the widest gap. The winner is 2.1444,
with dev balanced accuracy 0.817 (dev false-answer rate 8.3%,
false-abstention rate 28.2%). The full sweep is in
`data/results/relevance_floor_sweep.csv`. The test half was not looked at
during calibration.

**Why stale queries get `answer_conditionally` (option a, not
relabelling).** The 8 stale documents exist to test an age signal that is
separate from supersession, and "answer, but flag that the source is old"
is the right behaviour for a user. So the labels stay as they are, and
freshness triggers the mode. The floor was fixed at e⁻¹ from the existing
`FRESHNESS_SCALE` instead of being fitted. The freshness values were seen
before it was fixed, though, and the margin is narrow. The youngest stale
document at top-1 is the 2021 org chart (F = 0.338). The oldest non-stale
top-1 is `hr-wfh-policy-v1` (F = 0.413), which is the correct version for
pre-2025 joiners and must not be flagged.

#### Results

Test (held out, 53 queries):

| Expected \ predicted | answer | answer_conditionally | abstain |
|---|---|---|---|
| answer (37) | 25 | 0 | 12 |
| answer_conditionally (4) | 0 | 3 | 1 |
| abstain (12) | 0 | 0 | 12 |

False-answer rate **0%** (0/12), false-abstention rate **32.4%** (12/37),
mode accuracy 75.5%.

Dev (used for calibration, 55 queries): false-answer 8.3% (1/12),
false-abstention 28.2% (11/39), mode accuracy 74.5%.

All 108 queries:

| Expected \ predicted | answer | answer_conditionally | abstain |
|---|---|---|---|
| answer (76) | 53 | 0 | 23 |
| answer_conditionally (8) | 0 | 5 | 3 |
| abstain (24) | 1 | 0 | 23 |

False-answer rate 4.2% (1/24), false-abstention rate 30.3% (23/76), mode
accuracy 75.0%. (`data/results/answer_mode_summary.csv`; per query, with
the top-1 relevance, freshness and doc, in
`data/results/answer_modes.csv`.)

**Reading the false abstentions.** In 20 of the 23, `provenance_rank`'s
top-1 is not from the gold document. The parking-fee queries (q036–q039),
the replacement-laptop queries (q033–q035) and several version_conflict
queries all have this pattern. On those 20, the floor is turning a wrong
answer into an abstention, so the false-abstention rate mostly reflects a
ranking miss rather than an over-cautious floor. Only 3 of the 23 (q077,
q080, q086) abstain when the gold document is at top-1. For comparison, 44
of the 53 answered `answer` queries have the gold document at top-1.

**The remaining errors.**
- **q053, the one false answer** ("How are performance ratings calibrated
  across teams?"). The restricted calibration guidelines are filtered out,
  but the in-scope `hr-performance-review-guide` scores 6.37 on the
  cross-encoder because it is on the same topic. This answer does not leak
  the restricted document. The cross-encoder judges topical relevance, not
  whether the chunk actually contains the answer.
- **3 stale queries abstain** (q065, q070, q071). In each, the freshness
  term has already pushed the stale gold document out of the top-1 (see
  Findings), so what is left is an unrelated page with low relevance.
  Abstaining is reasonable there, but the age flag never gets a chance to
  fire.

## Status

What exists so far:

- The 148-document corpus (versioned, ordinary, conflicting, restricted and
  stale), its manifest, and 6 user profiles.
- A validator and a conflict checker, both passing on the current corpus.
- Section-level chunking (`src/ingest.py`) and a supersession lookup, with
  `gold_chunk_id` in the manifest for every row that has a value (42 rows),
  checked by `scripts/check_chunks.py`.
- A smoke test confirming that BM25 and sentence-transformers are installed
  and working.
- A persistent ChromaDB index of all 991 chunks (`src/index_chunks.py`),
  embedded with `all-MiniLM-L6-v2` from `chunk_text`, with the full chunk
  metadata attached. List fields (`applies_if`, `conflicts_with`,
  `department_scope`) are stored as JSON strings, and null fields are
  omitted. Re-running the script rebuilds the collection.
- An annotated set of 108 evaluation queries (`data/queries.csv`), all
  verified.
- Five baseline retrievers (BM25, dense, hybrid RRF, cross-encoder rerank,
  recency prior) and the proposed method (`src/retrievers.py`): a scope
  filter followed by provenance-aware scoring with relevance, authority,
  freshness and a conflict penalty (DELTA = 0.4), plus the three answer
  modes (`provenance_answer`), with a cross-encoder relevance floor
  calibrated on a dev split and a freshness floor for stale sources.
- An evaluation harness (`src/evaluate.py`) and its results (see Results).

Not built yet: ablations of the scoring terms, and a variant of the method that
uses dense as its base retriever. pandas and scikit-learn are installed but
not used by any code yet.
