# Handover

Last updated: 2026-11-19

## Done

- **Embeddings and Chroma indexing.** `src/index_chunks.py` embeds all 991
  chunks from `data/chunks.jsonl` with `all-MiniLM-L6-v2` and writes them,
  with full chunk metadata, to the persistent collection in `data/chroma/`
  (not in git; re-run the script to rebuild).
- **Metadata filtering verified.** `scripts/smoke_test_index.py` runs the query
  "how many leave days can I carry forward" unfiltered and with
  `where={"status": "current"}`, and asserts that the filter lets nothing
  through except `status=current`.
- **Smoke test result.** The current and superseded Annual Leave Policy chunks
  come back at cosine distances 0.197 and 0.200. Similarity cannot separate
  the versions, and a status filter gives the wrong answer to pre-1 April 2025
  joiners, so version choice has to come from `applies_if` checked against the
  user profile. (Written up in the README under evaluation design.)
- **Annotated query set.** `data/queries.csv` has 108 verified queries in
  seven categories. 84 have a gold chunk; the 24 leakage-probe and
  unanswerable queries are expected to abstain.
- **Baselines.** `src/retrievers.py` has BM25, dense, hybrid RRF,
  cross-encoder rerank and a recency prior. None of them reads the user
  profile.
- **Proposed method.** `scoped_search` filters out chunks the user may not
  see (`provenance.in_scope`), and `provenance_rank` scores the scoped pool
  with `ALPHA*rel + BETA*A + GAMMA*F`, where A is authority for the user and
  F is freshness.
- **Evaluation.** `python src/evaluate.py` writes `data/results/`. Provenance
  rank: Recall@5 0.786, MRR 0.691, IER 0%, SVR 0%. Hybrid: Recall@5 0.821,
  IER 26.9%, SVR 22.2%. Findings are written up in the README under Results.

- **Conflict penalty and answer modes.** DELTA = 0.4; lower side chosen by
  (A, is policy_version, effective_date). Contradicting page out of the top 5
  for all 12 cross_doc_conflict queries (`tests/test_conflicts.py`). On
  their own, conflicts gave every query `answer` (false-answer rate 100%).

- **Relevance and freshness floors.** `answer_mode` abstains when the
  cross-encoder logit of (query, top-1) is below RELEVANCE_FLOOR = 2.1444,
  fitted on the dev half of `data/query_split.csv` by
  `scripts/calibrate_relevance_floor.py`. It returns answer_conditionally
  when top-1 freshness < e^-1 (more than 5 years old). Held-out test:
  false-answer 0% (0/12), false-abstention 32.4% (12/37). All 108:
  4.2% / 30.3%, mode accuracy 75.0%. 20 of the 23 false abstentions have a
  non-gold doc at top-1. See README > Answer modes.

- **Ablations, both bases** (`scripts/run_ablations.py`, `data/results/ablations*.csv`).
  Authority earns its place: with BETA = 0, user_dependent IER goes 0 -> 10.5%
  on the hybrid base and 0 -> 21.1% on dense. Freshness does not: GAMMA = 0
  improves MRR, recall@5 and nDCG on both bases, and every category including
  stale (0.7812 -> 0.7917) and version_conflict. Conflict penalty is
  base-dependent: no effect on hybrid (-0.0016 MRR) but -0.0139 overall and
  -0.0333 on version_conflict with dense, so DELTA stays.

- **Dense base adopted.** version_conflict was the binding constraint: MRR
  0.4285 and recall@5 0.5500, identical across all three hybrid-base
  ablations, i.e. a base-retrieval failure, not a provenance failure - no
  re-weighting can promote a chunk that was never retrieved. On dense:
  recall@5 0.9048, MRR 0.8538, nDCG 0.8563, latency 7.6ms (was 12.9).
  Against the dense baseline, MRR +11 points with IER@1 30.6% -> 0%.

- **Relevance floor recalibrated** 2.1444 -> 1.8979 for the new base, dev
  split only. False abstention 30.3% -> 18.4%; held-out test false-answer
  rate still 0%. The floor is base-dependent and must be refitted whenever
  the base or the weights change.

- **IER reported at two ranks.** ier@1 (top-1 chunk inapplicable; the
  original metric, unchanged) and ier@5 (any of top-5). provenance_rank:
  0.0000 / 0.0741. Dense baseline: 0.3056 / 0.6574. The 7.4% is by design -
  both versions of a policy are retrieved, because a superseded version
  still governs part of the workforce, and the applicable one is ranked
  first every time. Reporting both pre-empts the circularity objection.

- **Determinism** (`scripts/check_determinism.py`). Five runs in fresh
  processes: 107/108 queries returned an identical top-5; one varied at
  ranks 4-5 among non-gold chunks. All metrics had zero spread. Likely
  cause: Chroma's approximate index returns a slightly different candidate
  pool, and rel is min-max normalised over that pool. Not fixed - it moves
  no metric.

- **Generation layer** (`src/generate.py`). Provider-agnostic (anthropic /
  openai / azure / ollama via LLM_PROVIDER), temperature 0, every response
  cached in `data/generation_cache/`. Abstain never calls the LLM, so
  hallucination is impossible on abstained queries by construction.
  Citations are chunk_ids, which makes citation accuracy mechanically
  checkable against gold_chunk_id with no judge.

- **Generation metrics** (`scripts/evaluate_generation.py`). Run on
  llama3 via Ollama. citation_accuracy 0.9070, uncited_claim_rate 0.0000,
  abstain_compliance 1.0000. user_dependent: citation accuracy 1.0000.

- **Citation guard and fabrication pattern.** 10% of answers cited a
  chunk_id not in the retrieved set; the guard strips them and flags any
  claim left uncited (6 of 70 answers). Five of the seven fabrications were
  the RIGHT document with an invented section number (q006, q081, q092,
  q095); only q096 cited a wholly unrelated document. Hypothesis, untested:
  the ::sNNpN format is hard for an 8B model to reproduce verbatim, and
  numbered references mapped back to chunk_ids in code would remove most
  of it. Fabrication is 0% in user_dependent, cross_doc_conflict and
  leakage_probe, and 26.3% in ordinary.

- **Applicability in the prompt.** Each chunk header is now marked
  [APPLIES TO YOU] / [DOES NOT APPLY TO YOU] (from authority; no profile
  attribute reaches the prompt) and the system prompt says to answer only
  from applicable chunks. Pre-fix answers were rescored from cache by
  `scripts/score_preapplicability.py`. Inapplicable chunk cited: **1 of 11
  -> 0 of 11** (the 11 answered queries where an inapplicable chunk reached
  the prompt; 1.4% -> 0% of all 70 answers). **11 opportunities is too few
  to demonstrate the fix** - one event going to zero is consistent with
  noise. Report it as "no regression, and the one observed case is gone",
  not as an effect.

  The one pre-fix case, q008 (version_conflict, mode answer): "What are
  the password requirements?", asked by u004 (Finance, G4, Bengaluru,
  full_time, joined 2025-02-10). Cited `it-password-rules-v1::s01p0`
  (rank 3). v1 has no applies_if and is superseded by v2 (effective
  2025-09-01, also unconditional), so it governs nobody, u004 included
  (authority 0.3). Pre-fix, the model gave v2's 14-character minimum
  correctly but co-cited v1 alongside v2 on the passphrase line (identical
  in both versions), then added a contradictory note that 12 characters is
  not mentioned. Post-fix (both formats) it cites only v2 and drops the
  note. A harmless co-citation, not a wrong value reaching the user - say
  so rather than present it as a near-miss.

- **Citation-format A/B, three-way** (llama3 / Ollama, same 108 queries,
  same retrieval; `generation_preapplicability.csv`, `generation.csv`,
  `generation_numbered.csv`):

  | metric                     | chunk_id pre-fix | chunk_id post-fix | numbered |
  |----------------------------|------------------|-------------------|----------|
  | citation_accuracy          | 0.9070           | 0.9070            | 0.9070   |
  | cited_chunk_retrieved      | 0.9000           | 0.9571            | 1.0000   |
  | fabricated_citation_rate   | 10.0% (7/70)     | 4.3% (3/70)       | 0.0%     |
  | uncited_claim_rate         | 0                | 0                 | 0        |
  | abstain_compliance         | 1.0000           | 1.0000            | 1.0000   |
  | inapplicable cited (of 11) | 1                | 0                 | 0        |

  Numbered matches or beats chunk_id on every metric and loses nothing, so
  it is now the default `CITATION_FORMAT`. The finding: fabrication went
  10% -> 4.3% -> 0%. Be careful with attribution: the first step came with
  the applicability change (a prompt change, not a format change), so the
  clean format effect is post-fix chunk_id vs numbered, 3/70 -> 0/70
  (q006, q067, q088 under chunk_id). Small numbers, one model; frame it as
  consistent with the "verbatim ::sNNpN is hard for an 8B model"
  hypothesis, not proof of it. Citation accuracy is identical across all
  three, so numbered removes invented IDs without changing which chunk
  gets cited.

  `CITATION_FORMAT=chunk_id` still selects the old format. Output names
  follow the format, not the default: chunk_id writes `generation*.csv`,
  numbered writes `generation_numbered*.csv`. Both are committed and both
  reproduce byte-for-byte from `data/generation_cache/` with no network
  (checked 2026-11-19 with OLLAMA_HOST pointed at a dead port).

- **Reproducibility caveat: Ollama timeouts.** On CPU-only Ollama a single
  llama3 call can exceed the 300 s per-call limit (`TIMEOUT` in
  `src/generate.py`) partway through a run, which aborts the run. Every
  completed response is already in the disk cache, so re-running the same
  command resumes where it stopped and repeats no calls. A fresh
  reproduction may need several restarts; that is expected, not a bug.

## Next

Items 0-4 are done. Experimental work is complete; what remains is writing
and the optional demonstration layer.

1. **Dissertation write-up.** Results, discussion, conclusion, and fold in
   everything since the mid-semester report. This is the critical path.
2. **Pilot study** (Sat 21 Nov). Six to eight recent joiners, five real
   questions each, recording correct / incorrect / escalated per answer.
   ~35 data points: reportable, not significant. Say so.
3. **FastAPI and Copilot Studio.** Demonstration layer, not a research
   claim. Cut first if time is short.
4. ~~A/B the citation format.~~ Done; see the three-way table above.
5. **Housekeeping.** `ablations.csv` still uses the old
   `invalid_evidence_rate` column name; re-running `run_ablations.py`
   picks up ier@1/ier@5. And `resolve_provider()` runs before the cache
   lookup, so reproducing generation results needs LLM_PROVIDER set even
   though no network call happens - moving it after the lookup would make
   the cached results reproducible with no API access at all.

## Constraints

- **Chunking config is frozen.** Any change to chunking in `src/ingest.py`
  (e.g. `MAX_WORDS`, section/heading rules) regenerates all 42
  `gold_chunk_id`s in the manifest. If it ever has to change, re-run
  `python scripts/check_chunks.py --write-gold` and re-check every
  annotated query against the new IDs.

- **The mid-semester report and viva deck cite hybrid-base numbers**
  (recall@5 0.7857, MRR 0.6928, IER 0.0000 at top-1). Those were correct
  when submitted and are preserved as the `provenance_rank` row in
  `data/results/ablations.csv`. In the dissertation, frame the dense base
  as a progression from the mid-semester configuration, not as a
  correction. Note also that the deck's slide 9 described IER as a top-5
  metric when the implementation was top-1; the dissertation must use the
  ier@1 / ier@5 split.

- **RELEVANCE_FLOOR is base- and weight-dependent.** Any change to the
  base retriever, ALPHA, BETA, GAMMA or DELTA invalidates it. Refit with
  `scripts/calibrate_relevance_floor.py` on the dev split only, and report
  on test.
