"""Calibrate retrievers.RELEVANCE_FLOOR on the dev split.

For each dev query whose expected_behaviour is answer or abstain (stale
queries are left out: their expected mode is answer_conditionally, which the
relevance floor does not decide), compute top_relevance: the cross-encoder
logit of (query, provenance_rank top-1 chunk_text).

Candidate thresholds are the midpoints between adjacent distinct scores. A
query abstains when its score is below the threshold. The chosen threshold
maximises balanced accuracy,

    0.5 * (share of abstain queries below it + share of answer queries at or above it),

which weights the 12 abstain and 39 answer dev queries equally rather than
letting the larger class dominate. Ties go to the candidate with the widest
gap between the two scores it sits between, i.e. the one furthest from any
dev query.

Test queries are never read. Writes data/results/relevance_floor_sweep.csv
(one row per candidate) and prints the chosen value; copy it into
retrievers.RELEVANCE_FLOOR.

Usage: python scripts/calibrate_relevance_floor.py
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrievers import ABSTAIN, ANSWER, provenance_rank, top_relevance  # noqa: E402

QUERIES_IN = ROOT / "data" / "queries.csv"
SPLIT_IN = ROOT / "data" / "query_split.csv"
PROFILES_IN = ROOT / "data" / "user_profiles.json"
SWEEP_OUT = ROOT / "data" / "results" / "relevance_floor_sweep.csv"


def dev_scores():
    with SPLIT_IN.open(encoding="utf-8", newline="") as f:
        split = {r["query_id"]: r["split"] for r in csv.DictReader(f)}
    with PROFILES_IN.open(encoding="utf-8") as f:
        profiles = {p["user_id"]: p for p in json.load(f)}
    with QUERIES_IN.open(encoding="utf-8", newline="") as f:
        queries = [q for q in csv.DictReader(f)
                   if split[q["query_id"]] == "dev"
                   and q["expected_behaviour"] in (ANSWER, ABSTAIN)]
    rows = []
    for q in queries:
        hits = provenance_rank(q["question"], profiles[q["asking_user_id"]], 1)
        rows.append((top_relevance(q["question"], hits), q["expected_behaviour"]))
    return rows


def sweep(rows):
    scores = sorted({s for s, _ in rows})
    n_abstain = sum(1 for _, e in rows if e == ABSTAIN)
    n_answer = len(rows) - n_abstain
    out = []
    for lo, hi in zip(scores, scores[1:]):
        t = (lo + hi) / 2
        abstain_hit = sum(1 for s, e in rows if e == ABSTAIN and s < t) / n_abstain
        answer_hit = sum(1 for s, e in rows if e == ANSWER and s >= t) / n_answer
        out.append({"threshold": t, "gap": hi - lo,
                    "false_answer_rate": 1 - abstain_hit,
                    "false_abstention_rate": 1 - answer_hit,
                    "balanced_accuracy": (abstain_hit + answer_hit) / 2})
    return out, n_abstain, n_answer


def main():
    rows = dev_scores()
    candidates, n_abstain, n_answer = sweep(rows)
    best = max(candidates, key=lambda c: (round(c["balanced_accuracy"], 9), c["gap"]))

    SWEEP_OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = list(candidates[0])
    with SWEEP_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in candidates:
            w.writerow({k: f"{v:.4f}" for k, v in c.items()})

    print(f"dev queries: {n_abstain} abstain, {n_answer} answer")
    print(f"chosen RELEVANCE_FLOOR = {best['threshold']:.4f} "
          f"(gap {best['gap']:.4f})")
    print(f"  dev balanced accuracy  {best['balanced_accuracy']:.4f}")
    print(f"  dev false-answer rate  {best['false_answer_rate']:.4f}")
    print(f"  dev false-abstention   {best['false_abstention_rate']:.4f}")
    print(f"sweep written to {SWEEP_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
