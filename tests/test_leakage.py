"""Leakage check: scoped_search must never return the must_not_use_doc_id of a
leakage_probe query to the asking user.

Run directly for a pass/fail line per query (exit 1 on any failure), or under
pytest.

Usage: python tests/test_leakage.py [k]
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERIES_IN = ROOT / "data" / "queries.csv"
sys.path.insert(0, str(ROOT / "src"))

from provenance import load_profiles  # noqa: E402
from retrievers import scoped_search  # noqa: E402

DEFAULT_K = 10


def leakage_probes():
    with QUERIES_IN.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["category"] == "leakage_probe"]


def check(k=DEFAULT_K):
    profiles = load_profiles()
    results = []
    for row in leakage_probes():
        hits = scoped_search(row["question"], profiles[row["asking_user_id"]], k)
        leaked = [h["chunk_id"] for h in hits
                  if h["metadata"]["doc_id"] == row["must_not_use_doc_id"]]
        results.append((row, len(hits), leaked))
    return results


def test_no_leakage():
    results = check()
    assert len(results) == 12
    assert not [r["query_id"] for r, _, leaked in results if leaked]


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_K
    results = check(k)
    for row, n, leaked in results:
        status = "FAIL" if leaked else "PASS"
        print(f"{status}  {row['query_id']}  {row['asking_user_id']}  "
              f"{row['must_not_use_doc_id']:<40} returned={n} leaked={len(leaked)}")
    failed = sum(1 for *_, leaked in results if leaked)
    print(f"\n{len(results) - failed}/{len(results)} passed (k={k})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
