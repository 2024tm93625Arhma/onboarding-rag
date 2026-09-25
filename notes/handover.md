# Handover

Last updated: 2026-09-25

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

## Next

1. **Build the annotated query set** from `corpus/manifest.csv`, using the
   `gold_chunk_id` column (42 rows with a value) as the expected answers.
2. **Build the baseline retrievers** (BM25 and dense over the Chroma index).

## Constraints

- **Chunking config is frozen.** Any change to chunking in `src/ingest.py`
  (e.g. `MAX_WORDS`, section/heading rules) regenerates all 42
  `gold_chunk_id`s in the manifest. If it ever has to change, re-run
  `python scripts/check_chunks.py --write-gold` and re-check every
  annotated query against the new IDs.
