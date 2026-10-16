# Handover

Last updated: 2026-10-16

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
  for all 12 cross_doc_conflict queries (`tests/test_conflicts.py`). Answer
  modes: false-answer rate 100% (24/24), false-abstention rate 0% (0/76).
  Every query gets `answer`; see README > Answer modes for why.

## Next

0. **Evidence-sufficiency abstention.** The conflict signal never triggers
   abstain (see README). Needs a separate signal; avoid tuning its threshold
   on the evaluation queries.
1. ~~**Conflict detection.**~~ Done. For the top-k chunks, find pairs from different
   policy families whose `conflicts_with` lists each other, and apply
   C(d,D) to the lower-authority chunk with DELTA = 0.4 (DELTA is 0 now).
   A helper `provenance.in_conflict(a, b)` is drafted but not yet used.
   Note that `authority` gives a standalone document 1.0 whenever it
   applies, so a crib sheet and the current policy it contradicts usually
   tie on authority. Decide how to break that tie before relying on
   "lower-authority".
2. ~~**Answer modes.**~~ Done; see above. answer / answer_conditionally / abstain, chosen by
   whether conflicting chunks of comparable authority remain after scoring.
   Evaluate the false-answer rate on the 24 abstain queries and the
   false-abstention rate on the 76 answer queries. A conflict signal alone
   is unlikely to make leakage-probe and unanswerable queries abstain,
   because those queries fail through missing evidence, not conflicting
   evidence.
3. **Ablations.** Drop each of authority, freshness and (once it exists) the
   conflict penalty in turn and re-run the evaluation. The freshness ablation
   matters in particular: GAMMA = 0 restores rank 1 for stale queries q065
   and q070.
4. **Dense-base variant.** Run scoped_search and provenance_rank on top of
   dense instead of hybrid. Dense has the best baseline recall (0.929), so
   it may recover the 3.6-point Recall@5 cost.

## Constraints

- **Chunking config is frozen.** Any change to chunking in `src/ingest.py`
  (e.g. `MAX_WORDS`, section/heading rules) regenerates all 42
  `gold_chunk_id`s in the manifest. If it ever has to change, re-run
  `python scripts/check_chunks.py --write-gold` and re-check every
  annotated query against the new IDs.
