"""Check whether provenance_rank is reproducible across runs.

Runs provenance_rank (default configuration) over all queries N_RUNS times,
each run in a fresh Python process, so models, indexes and caches are
reloaded every time, as they are when scripts are run separately. Within a
run each query is ranked at k=5 and k=10, as in src/evaluate.py, and scored
with src/evaluate.py's evaluate_query / aggregate (reused, not copied).

Reports:
- queries whose top-5 chunk_id list was identical in every run
- queries whose top-5 varied, and for each the ranks whose chunk differed
  from run 1 in at least one run, with the scores at those ranks
- queries whose top-5 SET of chunks differed (not just reordered)
- min / max / spread of recall@5, MRR, nDCG@10, IER and SVR across runs

Prints a summary only. Per-run output goes to a temporary directory that is
deleted at the end; nothing is written to data/results/.

Usage: python scripts/check_determinism.py [--runs 5]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

N_RUNS = 5
SUMMARY_METRICS = [("recall@5", "recall@5"), ("mrr", "MRR"), ("ndcg@10", "nDCG@10"),
                   ("ier@1", "IER"), ("scope_violation_rate", "SVR")]


# --------------------------------------------------------------------- worker

def worker(out_path):
    """One run: rank every query at k=5 and k=10, write ids, scores, metrics."""
    from evaluate import (KS, aggregate, evaluate_query, gold_ids, load_profiles,
                          load_queries)
    from retrievers import _chunks, provenance_rank

    queries = load_queries()
    profiles = load_profiles()
    chunks = _chunks()
    per_query, rows = {}, []
    for q in queries:
        user = profiles[q["asking_user_id"]]
        ranked = {k: provenance_rank(q["question"], user, k) for k in KS}
        hits = {k: (ranked[k], 0.0) for k in KS}
        rows.append(evaluate_query(q, user, gold_ids(q, chunks), hits))
        per_query[q["query_id"]] = {
            "top5": [h["chunk_id"] for h in ranked[5]],
            "scores5": [h["score"] for h in ranked[5]],
        }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"queries": per_query, "metrics": aggregate(rows)}, f)


# --------------------------------------------------------------------- report

def run_all(n_runs, tmp):
    runs = []
    for i in range(n_runs):
        out = Path(tmp) / f"run{i}.json"
        print(f"run {i + 1}/{n_runs} (fresh process)...", file=sys.stderr, flush=True)
        subprocess.run([sys.executable, __file__, "--worker", str(out)],
                       check=True, cwd=ROOT)
        with out.open(encoding="utf-8") as f:
            runs.append(json.load(f))
    return runs


def report(runs):
    n = len(runs)
    qids = list(runs[0]["queries"])
    identical, varied, set_changed = [], [], []
    for qid in qids:
        lists = [r["queries"][qid]["top5"] for r in runs]
        if all(l == lists[0] for l in lists):
            identical.append(qid)
            continue
        varied.append(qid)
        if any(set(l) != set(lists[0]) for l in lists):
            set_changed.append(qid)

    print(f"\nprovenance_rank determinism: {len(qids)} queries x {n} runs "
          "(each run a fresh process, default configuration)")
    print(f"  identical top-5 list in every run: {len(identical)}")
    print(f"  top-5 varied:                      {len(varied)}")
    print(f"    of which top-5 SET changed:      {len(set_changed)}")
    print(f"    of which reordered only:         {len(varied) - len(set_changed)}")

    if varied:
        print("\nVaried queries (ranks whose chunk differed from run 1 in some run):")
        for qid in varied:
            lists = [r["queries"][qid]["top5"] for r in runs]
            scores = [r["queries"][qid]["scores5"] for r in runs]
            width = max(len(l) for l in lists)
            moved = [i for i in range(width)
                     if len({l[i] if i < len(l) else None for l in lists}) > 1]
            n_variants = len({tuple(l) for l in lists})
            tag = "SET CHANGED" if qid in set_changed else "reordered"
            print(f"  {qid}  [{tag}]  ranks moved: {', '.join(str(i + 1) for i in moved)}"
                  f"  ({n_variants} distinct orderings)")
            for i in moved:
                cells = [f"{l[i] if i < len(l) else '-'} ({s[i]:.6f})" if i < len(l) else "-"
                         for l, s in zip(lists, scores)]
                print(f"      rank {i + 1}: " + " | ".join(cells))

    print(f"\nMetric spread across {n} runs (all queries; recall/MRR/nDCG over ranked queries):")
    print(f"  {'metric':<9} {'min':>8} {'max':>8} {'spread':>8}")
    for key, label in SUMMARY_METRICS:
        vals = [r["metrics"][key] for r in runs]
        print(f"  {label:<9} {min(vals):8.4f} {max(vals):8.4f} {max(vals) - min(vals):8.4f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=N_RUNS)
    parser.add_argument("--worker", metavar="OUT_JSON", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    with tempfile.TemporaryDirectory() as tmp:
        report(run_all(args.runs, tmp))


if __name__ == "__main__":
    main()
