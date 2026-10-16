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

scoped_search(query, profile, k, base) is not a baseline: it runs a base
retriever SCOPE_DEPTH deep, drops chunks the profile may not see
(provenance.in_scope) and returns the top k of what remains.

provenance_rank(query, profile, k) is the provenance-aware ranker. It scores
each chunk of scoped_search's SCOPE_DEPTH pool with

    score(q, d, u) = ALPHA*rel(q,d) + BETA*A(d,u) + GAMMA*F(d,t) - DELTA*C(d,D)

- rel: the hybrid RRF score, min-max normalised across the scoped pool.
- A:   authority for this user. 1.0 if d applies to u and no other version in
       d's policy family both applies to u and has a later effective_date; 0.3
       if d applies but such a later version exists; 0.0 if d does not apply.
       Family membership is taken from the whole corpus, not the pool, so a
       later version counts even when none of its chunks were retrieved.
       Standalone docs are families of one and so get 1.0 when they apply.
- F:   freshness, exp(-age_in_years / FRESHNESS_SCALE) with age measured from
       effective_date to REFERENCE_DATE.
- C:   conflict penalty. The pool is first ranked without C. In its top
       CONFLICT_K, every pair of chunks that declare a conflict with each other
       (provenance.in_conflict: different policy families, each doc's
       conflicts_with lists the other) is found. C(d,D) = 1 if d is the lower-
       precedence side of at least one such pair, else 0, and the pool is
       re-ranked with the penalty. One pass: chunks that enter the top
       CONFLICT_K only after re-ranking are not checked again.

       Precedence is the key (A, is policy_version, effective_date), compared
       in that order. Authority alone does not separate the declared pairs: a
       standalone doc gets A = 1.0 whenever it applies, so a crib sheet and the
       current policy it contradicts tie. The tie goes to the formal policy
       version over the derivative page, then to the later effective_date. A
       pair equal on all three has no lower side and neither chunk is
       penalised. conflicts_with is document-level, so every chunk of the
       losing doc in the window is penalised, not only the one that restates
       the value.
Each result carries "rel", "authority", "freshness" and "conflict" alongside
"score".

provenance_answer(query, profile, k) runs provenance_rank and picks an answer
mode from its top ANSWER_K (see answer_mode):

- answer:               no declared-conflict pair of comparable authority
                        (|A(a) - A(b)| <= AUTHORITY_TOLERANCE) remains in the
                        window after scoring.
- answer_conditionally: such a pair remains, but the top-1 chunk is not its
                        lower-precedence side: answer from the top-1 and flag
                        the contradicting source.
- abstain:              such a pair remains and the top-1 chunk is its lower-
                        precedence side, or the pair has no lower side; or the
                        scoped pool is empty.

A pair whose authorities differ by more than the tolerance is treated as
resolved: authority already says which side governs this user.

Models, the BM25 index and the chunk table load on first use and are cached
for the life of the process. Heavy imports (sentence-transformers, chromadb,
index_chunks) are deferred so that BM25 works without them.

Usage: python src/retrievers.py ["query"]
"""

import json
import math
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_IN = ROOT / "data" / "chunks.jsonl"
sys.path.insert(0, str(ROOT / "src"))

from provenance import applies_to, in_conflict, in_scope, policy_family  # noqa: E402

CROSS_ENCODER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60
FUSION_DEPTH = 100  # how deep each list goes into RRF
RERANK_POOL = 20    # hybrid candidates passed to the cross-encoder / recency prior
SCOPE_DEPTH = 100   # base-retriever depth scoped_search filters before truncating

# provenance_rank weights and constants
ALPHA = 1.0   # relevance
BETA = 0.6    # authority
GAMMA = 0.2   # freshness
DELTA = 0.4   # conflict penalty
AUTHORITY_CURRENT = 1.0     # applies, and no later applicable version in the family
AUTHORITY_SUPERSEDED = 0.3  # applies, but a later applicable version exists
AUTHORITY_NOT_APPLICABLE = 0.0
FRESHNESS_SCALE = 5.0       # years; F = exp(-age / FRESHNESS_SCALE)
REFERENCE_DATE = date(2026, 9, 1)
DAYS_PER_YEAR = 365.25
CONFLICT_K = 10             # top-k of the unpenalised ranking searched for conflicts
ANSWER_K = 5                # window answer_mode inspects
AUTHORITY_TOLERANCE = 0.1   # authorities within this are "comparable"

ANSWER = "answer"
ANSWER_CONDITIONALLY = "answer_conditionally"
ABSTAIN = "abstain"

TOKEN = re.compile(r"\w+")

DEMO_QUERY = "how many leave days can I carry forward"


def tokenize(text):
    return TOKEN.findall(text.lower())


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
def _family_versions():
    """family -> one representative chunk per doc_id in that family.

    applies_if and effective_date are document-level, so any chunk of a doc
    stands in for the whole doc.
    """
    families = {}
    for c in _chunks():
        families.setdefault(policy_family(c), {}).setdefault(c["metadata"]["doc_id"], c)
    return {fam: list(docs.values()) for fam, docs in families.items()}


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


def scoped_search(query, profile, k, base=hybrid_search):
    # Filter the deep pool, then truncate: filtering a top-k list would leave
    # fewer than k results whenever out-of-scope chunks ranked high.
    # Note that rerank and recency_prior cap their own pool at RERANK_POOL.
    pool = base(query, max(k, SCOPE_DEPTH))
    return [hit for hit in pool if in_scope(hit, profile)][:k]


def authority(chunk, profile):
    if not applies_to(chunk, profile):
        return AUTHORITY_NOT_APPLICABLE
    meta = chunk["metadata"]
    eff = date.fromisoformat(meta["effective_date"])
    for other in _family_versions()[policy_family(chunk)]:
        other_meta = other["metadata"]
        if other_meta["doc_id"] == meta["doc_id"]:
            continue
        if (date.fromisoformat(other_meta["effective_date"]) > eff
                and applies_to(other, profile)):
            return AUTHORITY_SUPERSEDED
    return AUTHORITY_CURRENT


def freshness(chunk, ref=REFERENCE_DATE):
    age_days = (ref - date.fromisoformat(chunk["metadata"]["effective_date"])).days
    return math.exp(-(age_days / DAYS_PER_YEAR) / FRESHNESS_SCALE)


def precedence(hit):
    """Key that orders the two sides of a declared conflict; higher wins."""
    meta = hit["metadata"]
    return (hit["authority"], meta["doc_kind"] == "policy_version", meta["effective_date"])


def conflict_pairs(hits):
    """(a, b, loser) for each declared-conflict pair in hits. loser is the
    lower-precedence of a and b, or None when they are equal on precedence."""
    pairs = []
    for i, a in enumerate(hits):
        for b in hits[i + 1:]:
            if not in_conflict(a, b):
                continue
            pa, pb = precedence(a), precedence(b)
            loser = None if pa == pb else (b if pa > pb else a)
            pairs.append((a, b, loser))
    return pairs


def _by_score(hits):
    # Ties broken by chunk_id so the order is deterministic.
    return sorted(hits, key=lambda h: (-h["score"], h["chunk_id"]))


def provenance_rank(query, profile, k):
    pool = scoped_search(query, profile, SCOPE_DEPTH)
    if not pool:
        return []
    raw = [hit["score"] for hit in pool]
    lo, hi = min(raw), max(raw)
    span = hi - lo
    scored = []
    for hit in pool:
        # A pool whose hybrid scores are all equal carries no relevance signal.
        rel = (hit["score"] - lo) / span if span > 0 else 1.0
        a = authority(hit, profile)
        f = freshness(hit)
        score = ALPHA * rel + BETA * a + GAMMA * f
        scored.append({**hit, "score": score, "rel": rel, "authority": a,
                       "freshness": f, "conflict": 0.0})
    scored = _by_score(scored)
    losers = {loser["chunk_id"] for *_, loser in conflict_pairs(scored[:CONFLICT_K])
              if loser is not None}
    for hit in scored:
        if hit["chunk_id"] in losers:
            hit["conflict"] = 1.0
            hit["score"] -= DELTA
    return _by_score(scored)[:k]


def answer_mode(hits):
    """answer / answer_conditionally / abstain for a ranked provenance_rank list."""
    if not hits:
        return ABSTAIN
    window = hits[:ANSWER_K]
    top = window[0]["chunk_id"]
    unresolved = [loser for a, b, loser in conflict_pairs(window)
                  if abs(a["authority"] - b["authority"]) <= AUTHORITY_TOLERANCE]
    if not unresolved:
        return ANSWER
    if any(loser is None or loser["chunk_id"] == top for loser in unresolved):
        return ABSTAIN
    return ANSWER_CONDITIONALLY


def provenance_answer(query, profile, k):
    hits = provenance_rank(query, profile, max(k, ANSWER_K))
    return answer_mode(hits), hits[:k]


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
