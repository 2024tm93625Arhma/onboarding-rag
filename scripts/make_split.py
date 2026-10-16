"""Split the query set into dev and test halves, stratified by category.

Within each category the queries are shuffled with a fixed seed and the first
ceil(n/2) go to dev, the rest to test. Thresholds (for example
retrievers.RELEVANCE_FLOOR) are calibrated on dev only; test is held out.

Writes data/query_split.csv (query_id, split). The split is frozen once
written: re-running with the same seed reproduces it.

Usage: python scripts/make_split.py
"""

import csv
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERIES_IN = ROOT / "data" / "queries.csv"
SPLIT_OUT = ROOT / "data" / "query_split.csv"
SEED = 20261016


def main():
    with QUERIES_IN.open(encoding="utf-8", newline="") as f:
        queries = list(csv.DictReader(f))
    by_category = {}
    for q in queries:
        by_category.setdefault(q["category"], []).append(q["query_id"])
    rng = random.Random(SEED)
    split = {}
    for cat in sorted(by_category):
        ids = sorted(by_category[cat])
        rng.shuffle(ids)
        n_dev = math.ceil(len(ids) / 2)
        for i, qid in enumerate(ids):
            split[qid] = "dev" if i < n_dev else "test"
    with SPLIT_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "split"])
        for q in queries:
            w.writerow([q["query_id"], split[q["query_id"]]])
    for cat in sorted(by_category):
        n_dev = sum(1 for qid in by_category[cat] if split[qid] == "dev")
        print(f"{cat:<20} dev {n_dev:>2}  test {len(by_category[cat]) - n_dev:>2}")


if __name__ == "__main__":
    main()
