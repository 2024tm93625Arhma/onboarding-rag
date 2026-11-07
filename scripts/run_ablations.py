"""Ablate the provenance_rank scoring terms.

Each variant is provenance_rank with one weight set to zero, the others left
at their module constants:

- no_authority: BETA = 0
- no_freshness: GAMMA = 0
- no_conflict:  DELTA = 0

plus one variant that changes the base retriever rather than a weight:

- provenance_rank_dense: scoped_search and provenance_rank over dense_search
  instead of hybrid_search, default weights. rel is then the dense cosine
  score, min-max normalised across the scoped pool.

The full method (no overrides) is included as the reference row, named
provenance_rank as in method.csv.

Queries, profiles, gold labels and metrics are those of src/evaluate.py (its
functions are reused, not copied), over all queries at k=5 and k=10.

Writes data/results/ablations.csv (one row per variant) and
data/results/ablations_by_category.csv (one row per variant x category), with
the columns of method.csv and method_by_category.csv. Prints both, and the
change in IER, Recall@5 and MRR of each ablation against the full method.

Usage: python scripts/run_ablations.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import (  # noqa: E402
    METRICS, RESULTS_DIR, evaluate_group, gold_ids, load_profiles, load_queries,
    print_table, write_csv)
from retrievers import _chunks, dense_search, provenance_rank  # noqa: E402

ABLATIONS_OUT = RESULTS_DIR / "ablations.csv"
ABLATIONS_BY_CATEGORY_OUT = RESULTS_DIR / "ablations_by_category.csv"
REFERENCE = "provenance_rank"

# name -> keyword overrides (weights, base) passed to provenance_rank
VARIANTS = {
    REFERENCE: {},
    "no_authority": {"beta": 0.0},
    "no_freshness": {"gamma": 0.0},
    "no_conflict": {"delta": 0.0},
    "provenance_rank_dense": {"base": dense_search},
}


def variant(overrides):
    return lambda query, profile, k: provenance_rank(query, profile, k, **overrides)


def main():
    queries = load_queries()
    profiles = load_profiles()
    chunks = _chunks()
    golds = {q["query_id"]: gold_ids(q, chunks) for q in queries}
    categories = sorted({q["category"] for q in queries})

    overall, by_category = evaluate_group(
        {name: variant(o) for name, o in VARIANTS.items()},
        queries, profiles, golds, categories)

    base_cols = ["retriever", "n_queries", "n_ranked", *METRICS]
    cat_cols = ["retriever", "category", "n_queries", "n_ranked", *METRICS]
    write_csv(ABLATIONS_OUT, overall, base_cols)
    write_csv(ABLATIONS_BY_CATEGORY_OUT, by_category, cat_cols)

    print_table(f"Ablations ({ABLATIONS_OUT.relative_to(ROOT)})", overall, base_cols)
    print_table(f"Ablations by category ({ABLATIONS_BY_CATEGORY_OUT.relative_to(ROOT)})",
                by_category, cat_cols)

    ref = next(r for r in overall if r["retriever"] == REFERENCE)
    deltas = [{"retriever": r["retriever"],
               "IER": r["invalid_evidence_rate"],
               "dIER": r["invalid_evidence_rate"] - ref["invalid_evidence_rate"],
               "Recall@5": r["recall@5"], "dRecall@5": r["recall@5"] - ref["recall@5"],
               "MRR": r["mrr"], "dMRR": r["mrr"] - ref["mrr"]}
              for r in overall]
    print_table(f"Change against {REFERENCE} (all {len(queries)} queries; "
                "Recall@5 and MRR over ranked queries only)",
                deltas, list(deltas[0]))


if __name__ == "__main__":
    main()
