"""Evaluate every retriever in retrievers.py over the frozen query set.

Two groups are evaluated: the baselines (retrievers.RETRIEVERS, called as
fn(query, k)) and the method retrievers (scoped_search and provenance_rank,
called as fn(query, profile, k) with the profile of the query's
asking_user_id).

Each retriever is run over all queries in data/queries.csv at k=5 and k=10.
Metrics, per retriever, overall and by query category:

- recall@5, recall@10: share of queries with at least one gold chunk in the
  top k (hit rate; most queries have a single gold chunk, so this is recall).
- mrr: 1 / rank of the first gold chunk in the top 10, 0 if none.
- ndcg@10: binary relevance; the ideal DCG assumes min(#gold chunks, 10)
  relevant chunks at the top.

  Gold is gold_chunk_id where present, else every chunk whose parent_doc_id
  is gold_doc_id. Queries with neither (abstain queries) have no gold and are
  left out of these four metrics; n_ranked counts the queries that are in.

- invalid_evidence_rate: share of queries whose top-1 chunk is invalid for
  the asking user: its applies_if conditions are not all satisfied by the
  user's profile, its parent doc is the query's must_not_use_doc_id, or it is
  out of the user's scope (see below).
- scope_violation_rate: share of queries where any chunk in the top 5 is out
  of the user's scope.

  A chunk is in scope when its department_scope contains "all" or the user's
  department, and the user's grade is at least its min_grade (if it has one).

  Both rates use every query, abstain queries included: an abstain query
  still retrieves evidence, and that evidence can still be invalid.

- latency_ms_k5, latency_ms_k10: mean wall-clock time per retriever call.
  One untimed warm-up call per retriever runs first, so model loading is not
  counted.

Answer modes: provenance_answer picks answer / answer_conditionally /
abstain for each query, scored against the query's expected_behaviour:

- false_answer_rate:     share of the abstain queries given any mode other
                         than abstain.
- false_abstention_rate: share of the answer queries given abstain.
- mode_accuracy:         share of all queries whose mode equals
                         expected_behaviour.

The 8 answer_conditionally (stale) queries count only in mode_accuracy.

retrievers.RELEVANCE_FLOOR was calibrated on the dev half of
data/query_split.csv (scripts/calibrate_relevance_floor.py), so answer-mode
results are reported separately for test (held out), dev and all queries. The
retrieval metrics involve no calibration and use all queries.

The baselines apply no scope filter, so scope_violation_rate is expected to
be non-zero. The method retrievers filter by scope, so it is expected to be 0.

Writes data/results/baselines.csv and data/results/method.csv (one row per
retriever) and data/results/by_category.csv and
data/results/method_by_category.csv (one row per retriever x category), and
data/results/answer_modes.csv (one row per query) and
data/results/answer_mode_summary.csv (one row per split) for the answer modes. It prints
them, and prints a comparison of every retriever's recall@5, IER
(invalid_evidence_rate) and SVR (scope_violation_rate).

Usage: python src/evaluate.py
"""

import csv
import json
import math
import operator
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrievers import (  # noqa: E402
    ABSTAIN, ANSWER, ANSWER_CONDITIONALLY, ANSWER_K, RETRIEVERS, _chunks,
    provenance_answer, provenance_rank, scoped_search)

QUERIES_IN = ROOT / "data" / "queries.csv"
SPLIT_IN = ROOT / "data" / "query_split.csv"
PROFILES_IN = ROOT / "data" / "user_profiles.json"
RESULTS_DIR = ROOT / "data" / "results"
BASELINES_OUT = RESULTS_DIR / "baselines.csv"
BY_CATEGORY_OUT = RESULTS_DIR / "by_category.csv"
METHOD_OUT = RESULTS_DIR / "method.csv"
METHOD_BY_CATEGORY_OUT = RESULTS_DIR / "method_by_category.csv"
ANSWER_MODES_OUT = RESULTS_DIR / "answer_modes.csv"
ANSWER_MODE_SUMMARY_OUT = RESULTS_DIR / "answer_mode_summary.csv"
SPLITS = ("test", "dev", "all")

# Profile-aware retrievers: fn(query, profile, k).
METHODS = {
    "scoped_search": scoped_search,
    "provenance_rank": provenance_rank,
}

KS = (5, 10)
WARMUP_QUERY = "warm-up"

OPS = {
    "==": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}

METRICS = ["recall@5", "recall@10", "mrr", "ndcg@10",
           "invalid_evidence_rate", "scope_violation_rate",
           "latency_ms_k5", "latency_ms_k10"]


# ------------------------------------------------------------------ loading

def load_queries():
    with QUERIES_IN.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_split():
    with SPLIT_IN.open(encoding="utf-8", newline="") as f:
        return {r["query_id"]: r["split"] for r in csv.DictReader(f)}


def load_profiles():
    with PROFILES_IN.open(encoding="utf-8") as f:
        return {p["user_id"]: p for p in json.load(f)}


def gold_ids(query, chunks):
    if query["gold_chunk_id"]:
        return {query["gold_chunk_id"]}
    if query["gold_doc_id"]:
        return {c["chunk_id"] for c in chunks if c["parent_doc_id"] == query["gold_doc_id"]}
    return set()


# ---------------------------------------------------------- validity checks

def grade_level(grade):
    return int(grade.lstrip("Gg"))


def in_scope(chunk, user):
    meta = chunk["metadata"]
    scope = meta["department_scope"]
    if "all" not in scope and user["department"] not in scope:
        return False
    min_grade = meta.get("min_grade")
    if min_grade and grade_level(user["grade"]) < grade_level(min_grade):
        return False
    return True


def applies_to(chunk, user):
    # join_date values are ISO strings, so string comparison orders them correctly.
    for cond in chunk["metadata"]["applies_if"]:
        actual = user.get(cond["field"])
        if actual is None or not OPS[cond["op"]](actual, cond["value"]):
            return False
    return True


def is_valid(chunk, user, must_not_use):
    return (applies_to(chunk, user)
            and chunk["parent_doc_id"] != must_not_use
            and in_scope(chunk, user))


# ------------------------------------------------------------ rank metrics

def first_hit_rank(ranked_ids, gold):
    for rank, cid in enumerate(ranked_ids, 1):
        if cid in gold:
            return rank
    return None


def ndcg(ranked_ids, gold, k):
    dcg = sum(1.0 / math.log2(rank + 1)
              for rank, cid in enumerate(ranked_ids[:k], 1) if cid in gold)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return dcg / idcg


# --------------------------------------------------------------- evaluation

def evaluate_query(query, user, gold, hits):
    """Per-query metric values. hits maps k -> (ranked chunk list, latency ms)."""
    top5, lat5 = hits[5]
    top10, lat10 = hits[10]
    must_not_use = query["must_not_use_doc_id"]
    row = {
        "latency_ms_k5": lat5,
        "latency_ms_k10": lat10,
        "invalid_evidence_rate": float(bool(top5) and not is_valid(top5[0], user, must_not_use)),
        "scope_violation_rate": float(any(not in_scope(c, user) for c in top5)),
    }
    if gold:
        ids5 = [c["chunk_id"] for c in top5]
        ids10 = [c["chunk_id"] for c in top10]
        rank = first_hit_rank(ids10, gold)
        row.update({
            "recall@5": float(first_hit_rank(ids5, gold) is not None),
            "recall@10": float(rank is not None),
            "mrr": 1.0 / rank if rank else 0.0,
            "ndcg@10": ndcg(ids10, gold, 10),
        })
    return row


def aggregate(rows):
    out = {"n_queries": len(rows),
           "n_ranked": sum(1 for r in rows if "mrr" in r)}
    for m in METRICS:
        vals = [r[m] for r in rows if m in r]
        out[m] = sum(vals) / len(vals) if vals else None
    return out


def run_retriever(fn, queries, profiles, golds):
    """fn takes (query, profile, k); baselines are wrapped to ignore the profile."""
    fn(WARMUP_QUERY, next(iter(profiles.values())), max(KS))
    per_query = []
    for q in queries:
        user = profiles[q["asking_user_id"]]
        hits = {}
        for k in KS:
            start = time.perf_counter()
            ranked = fn(q["question"], user, k)
            hits[k] = (ranked, (time.perf_counter() - start) * 1000)
        row = evaluate_query(q, user, golds[q["query_id"]], hits)
        row["category"] = q["category"]
        per_query.append(row)
    return per_query


# ------------------------------------------------------------------ output

def fmt(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: fmt(r[c]) for c in columns})


def print_table(title, rows, columns):
    cells = [[fmt(r[c]) if c in r else "" for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    print(f"\n{title}")
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def evaluate_group(retrievers, queries, profiles, golds, categories):
    """retrievers maps name -> fn(query, profile, k). Returns (overall, by_category)."""
    overall, by_category = [], []
    for name, fn in retrievers.items():
        print(f"running {name} over {len(queries)} queries...", file=sys.stderr)
        per_query = run_retriever(fn, queries, profiles, golds)
        overall.append({"retriever": name, **aggregate(per_query)})
        for cat in categories:
            rows = [r for r in per_query if r["category"] == cat]
            by_category.append({"retriever": name, "category": cat, **aggregate(rows)})
    return overall, by_category


def evaluate_answer_modes(queries, profiles, split):
    print(f"running provenance_answer over {len(queries)} queries...", file=sys.stderr)
    rows = []
    for q in queries:
        mode, hits, relevance = provenance_answer(
            q["question"], profiles[q["asking_user_id"]], ANSWER_K)
        rows.append({"query_id": q["query_id"], "split": split[q["query_id"]],
                     "category": q["category"],
                     "expected_behaviour": q["expected_behaviour"], "predicted_mode": mode,
                     "top_relevance": relevance,
                     "top_freshness": hits[0]["freshness"] if hits else None,
                     "top_doc_id": hits[0]["parent_doc_id"] if hits else ""})
    return rows


def in_split(rows, name):
    return rows if name == "all" else [r for r in rows if r["split"] == name]


def share(rows, pred):
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else None


def answer_mode_summary(rows):
    abstain = [r for r in rows if r["expected_behaviour"] == ABSTAIN]
    answer = [r for r in rows if r["expected_behaviour"] == ANSWER]
    false_answers = sum(1 for r in abstain if r["predicted_mode"] != ABSTAIN)
    false_abstentions = sum(1 for r in answer if r["predicted_mode"] == ABSTAIN)
    return {
        "n_queries": len(rows),
        "n_abstain": len(abstain),
        "false_answers": false_answers,
        "false_answer_rate": false_answers / len(abstain) if abstain else None,
        "n_answer": len(answer),
        "false_abstentions": false_abstentions,
        "false_abstention_rate": false_abstentions / len(answer) if answer else None,
        "mode_accuracy": share(rows, lambda r: r["predicted_mode"] == r["expected_behaviour"]),
    }


def mode_confusion(rows):
    modes = [ANSWER, ANSWER_CONDITIONALLY, ABSTAIN]
    return [{"expected": exp,
             **{f"pred_{m}": sum(1 for r in rows if r["expected_behaviour"] == exp
                                 and r["predicted_mode"] == m) for m in modes}}
            for exp in modes]


def profile_free(fn):
    return lambda query, profile, k: fn(query, k)


def main():
    queries = load_queries()
    profiles = load_profiles()
    chunks = _chunks()
    golds = {q["query_id"]: gold_ids(q, chunks) for q in queries}
    categories = sorted({q["category"] for q in queries})

    baselines, by_category = evaluate_group(
        {name: profile_free(fn) for name, fn in RETRIEVERS.items()},
        queries, profiles, golds, categories)
    method, method_by_category = evaluate_group(
        METHODS, queries, profiles, golds, categories)
    modes = evaluate_answer_modes(queries, profiles, load_split())
    mode_summaries = [{"split": name, **answer_mode_summary(in_split(modes, name))}
                      for name in SPLITS]

    base_cols = ["retriever", "n_queries", "n_ranked", *METRICS]
    cat_cols = ["retriever", "category", "n_queries", "n_ranked", *METRICS]
    write_csv(BASELINES_OUT, baselines, base_cols)
    write_csv(BY_CATEGORY_OUT, by_category, cat_cols)
    write_csv(METHOD_OUT, method, base_cols)
    write_csv(METHOD_BY_CATEGORY_OUT, method_by_category, cat_cols)
    mode_cols = list(modes[0])
    summary_cols = list(mode_summaries[0])
    write_csv(ANSWER_MODES_OUT, modes, mode_cols)
    write_csv(ANSWER_MODE_SUMMARY_OUT, mode_summaries, summary_cols)

    print_table(f"Baselines ({BASELINES_OUT.relative_to(ROOT)})", baselines, base_cols)
    print_table(f"By category ({BY_CATEGORY_OUT.relative_to(ROOT)})", by_category, cat_cols)
    print_table(f"Method ({METHOD_OUT.relative_to(ROOT)})", method, base_cols)
    print_table(f"Method by category ({METHOD_BY_CATEGORY_OUT.relative_to(ROOT)})",
                method_by_category, cat_cols)

    comparison = [{"retriever": r["retriever"], "Recall@5": r["recall@5"],
                   "IER": r["invalid_evidence_rate"], "SVR": r["scope_violation_rate"]}
                  for r in baselines + method]
    print_table("Comparison (all 108 queries; Recall@5 over ranked queries only)",
                comparison, ["retriever", "Recall@5", "IER", "SVR"])
    print_table(f"Answer modes ({ANSWER_MODE_SUMMARY_OUT.relative_to(ROOT)})",
                mode_summaries, summary_cols)
    for name in SPLITS:
        confusion = mode_confusion(in_split(modes, name))
        print_table(f"Answer modes, {name}: expected (rows) x predicted (columns)",
                    confusion, list(confusion[0]))


if __name__ == "__main__":
    main()
