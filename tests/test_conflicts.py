"""Conflict check: for every cross_doc_conflict query, provenance_rank must keep
the query's must_not_use_doc_id (the page restating a superseded value) out of
the top k, and the conflict precedence must favour the policy version over the
standalone page in every declared pair.

Run directly for a pass/fail line per query (exit 1 on any failure), or under
pytest.

Usage: python tests/test_conflicts.py [k]
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERIES_IN = ROOT / "data" / "queries.csv"
sys.path.insert(0, str(ROOT / "src"))

from provenance import in_conflict, load_profiles  # noqa: E402
from retrievers import _chunks, precedence, provenance_rank  # noqa: E402

DEFAULT_K = 5


def cross_doc_queries():
    with QUERIES_IN.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["category"] == "cross_doc_conflict"]


def declared_pairs():
    """One representative chunk per doc, paired across every declared conflict."""
    docs = {}
    for c in _chunks():
        docs.setdefault(c["metadata"]["doc_id"], c)
    reps = list(docs.values())
    return [(a, b) for i, a in enumerate(reps) for b in reps[i + 1:] if in_conflict(a, b)]


def check(k=DEFAULT_K):
    profiles = load_profiles()
    results = []
    for row in cross_doc_queries():
        hits = provenance_rank(row["question"], profiles[row["asking_user_id"]], k)
        bad = [h["chunk_id"] for h in hits
               if h["metadata"]["doc_id"] == row["must_not_use_doc_id"]]
        results.append((row, len(hits), bad))
    return results


def test_policy_wins_tie():
    pairs = declared_pairs()
    assert len(pairs) == 12
    for a, b in pairs:
        # Equal authority, as when both apply to the user: the policy must win.
        a, b = {**a, "authority": 1.0}, {**b, "authority": 1.0}
        policy = a if a["metadata"]["doc_kind"] == "policy_version" else b
        other = b if policy is a else a
        assert precedence(policy) > precedence(other)


def test_no_contradicting_page():
    results = check()
    assert len(results) == 12
    assert not [r["query_id"] for r, _, bad in results if bad]


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_K
    results = check(k)
    for row, n, bad in results:
        status = "FAIL" if bad else "PASS"
        print(f"{status}  {row['query_id']}  {row['asking_user_id']}  "
              f"{row['must_not_use_doc_id']:<40} returned={n} contradicting={len(bad)}")
    failed = sum(1 for *_, bad in results if bad)
    print(f"\n{len(results) - failed}/{len(results)} passed (k={k})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
