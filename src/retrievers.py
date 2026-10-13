"""Baseline retrievers over the chunk corpus.

Every retriever takes (query, k) and returns up to k chunks, best first. Each
result is the chunk dict from data/chunks.jsonl plus a "score" key (higher is
better; the scale depends on the retriever):

- bm25_search:   Okapi BM25 (rank_bm25) over chunk_text. Score = BM25 score.
- dense_search:  all-MiniLM-L6-v2 query embedding against the Chroma index in
                 data/chroma/. Score = cosine similarity (1 - cosine distance).
- hybrid_search: BM25 and dense fused with Reciprocal Rank Fusion,
                 score = sum over lists of 1 / (RRF_K + rank). Each list
                 contributes its top FUSION_DEPTH results.
- rerank:        hybrid's top RERANK_POOL re-ordered by the
                 cross-encoder/ms-marco-MiniLM-L-6-v2 on (query, chunk_text).
                 Score = cross-encoder logit.
- recency_prior: control condition. Hybrid's top RERANK_POOL, re-sorted so that
                 within each policy family the chunk with the latest
                 effective_date takes the family's best slot. The family's set
                 of slots does not change, so other chunks keep their place.
                 Score = the chunk's own hybrid score, which means scores are not
                 monotonic after re-sorting.

A policy family is the doc_id with its "-vN" suffix removed (hr-leave-policy-v1
and hr-leave-policy-v2 form the family hr-leave-policy). A standalone doc is a
family of its own, so its chunks never move.

These are the baselines. None of them reads applies_if, status or a user
profile.

Models, the BM25 index and the chunk table load on first use and are cached
for the life of the process. Heavy imports (sentence-transformers, chromadb,
index_chunks) are deferred so that BM25 works without them.

Usage: python src/retrievers.py ["query"]
"""

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_IN = ROOT / "data" / "chunks.jsonl"
sys.path.insert(0, str(ROOT / "src"))

CROSS_ENCODER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60
FUSION_DEPTH = 100  # how deep each list goes into RRF
RERANK_POOL = 20    # hybrid candidates passed to the cross-encoder / recency prior

TOKEN = re.compile(r"\w+")
VERSION_SUFFIX = re.compile(r"-v\d+$")

DEMO_QUERY = "how many leave days can I carry forward"


def tokenize(text):
    return TOKEN.findall(text.lower())


def policy_family(chunk):
    return VERSION_SUFFIX.sub("", chunk["parent_doc_id"])


def _result(chunk, score):
    return {**chunk, "score": float(score)}


# ---------------------------------------------------------------- cached state

@lru_cache(maxsize=1)
def _chunks():
    with CHUNKS_IN.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def _chunks_by_id():
    return {c["chunk_id"]: c for c in _chunks()}


@lru_cache(maxsize=1)
def _bm25():
    from rank_bm25 import BM25Okapi
    return BM25Okapi([tokenize(c["chunk_text"]) for c in _chunks()])


@lru_cache(maxsize=1)
def _embedder():
    from index_chunks import MODEL_NAME  # same model the index was built with
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def _collection():
    from index_chunks import get_collection
    return get_collection()


@lru_cache(maxsize=1)
def _cross_encoder():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(CROSS_ENCODER_NAME)


# ------------------------------------------------------------------ retrievers

def bm25_search(query, k):
    scores = _bm25().get_scores(tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    chunks = _chunks()
    return [_result(chunks[i], scores[i]) for i in order]


def dense_search(query, k):
    embedding = _embedder().encode([query], normalize_embeddings=True).tolist()
    res = _collection().query(query_embeddings=embedding, n_results=k,
                              include=["distances"])
    by_id = _chunks_by_id()
    return [_result(by_id[cid], 1.0 - dist)
            for cid, dist in zip(res["ids"][0], res["distances"][0])]


def hybrid_search(query, k):
    fused = {}
    for ranked in (bm25_search(query, FUSION_DEPTH), dense_search(query, FUSION_DEPTH)):
        for rank, hit in enumerate(ranked, 1):
            cid = hit["chunk_id"]
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    # Ties broken by chunk_id so the order is deterministic.
    order = sorted(fused, key=lambda cid: (-fused[cid], cid))[:k]
    by_id = _chunks_by_id()
    return [_result(by_id[cid], fused[cid]) for cid in order]


def rerank(query, k):
    pool = hybrid_search(query, RERANK_POOL)
    if not pool:
        return []
    scores = _cross_encoder().predict([(query, hit["chunk_text"]) for hit in pool])
    order = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)[:k]
    return [_result(pool[i], scores[i]) for i in order]


def recency_prior(query, k):
    pool = hybrid_search(query, max(k, RERANK_POOL))
    slots = {}
    for pos, hit in enumerate(pool):
        slots.setdefault(policy_family(hit), []).append(pos)
    reordered = [None] * len(pool)
    for positions in slots.values():
        members = [pool[p] for p in positions]
        # Stable sort: chunks with the same effective_date keep hybrid order.
        members.sort(key=lambda h: h["metadata"]["effective_date"], reverse=True)
        for pos, hit in zip(positions, members):
            reordered[pos] = hit
    return reordered[:k]


RETRIEVERS = {
    "bm25": bm25_search,
    "dense": dense_search,
    "hybrid": hybrid_search,
    "rerank": rerank,
    "recency_prior": recency_prior,
}


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else DEMO_QUERY
    print(f"query: {query!r}")
    for name, fn in RETRIEVERS.items():
        print(f"\n=== {name} ===")
        try:
            hits = fn(query, 5)
        except ImportError as e:
            print(f"  could not run: {e}")
            continue
        for rank, hit in enumerate(hits, 1):
            print(f"{rank}. {hit['parent_doc_id']:<32} {hit['score']:>9.4f}  {hit['chunk_id']}")


if __name__ == "__main__":
    main()
