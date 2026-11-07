"""Evaluate the generation layer (src/generate.py) over all queries.

Each query in data/queries.csv is run through answer_query(question,
profile of asking_user_id, k=5). LLM responses come from
data/generation_cache/ when present, so a re-run with unchanged retrieval and
prompts makes no LLM calls. The provider is taken from the environment as in
src/generate.py (e.g. LLM_PROVIDER=ollama LLM_MODEL=llama3).

Citations are every chunk_id-shaped token (<doc_id>::<chunk>) in the raw
answer text (raw_answer_text, before answer_query's citation guard strips
invalid citations), not only those that match a retrieved chunk, so
fabricated citations are visible. All metrics except fabricated_citation_rate
are therefore pre-guard.

Metrics (mechanical; no LLM judge):

- citation_accuracy:     share of non-abstained queries with a gold_chunk_id
                         whose answer cites the gold_chunk_id.
                         Denominator: n_gold.
- cited_chunk_retrieved: share of non-abstained answers with at least one
                         citation in which every cited chunk_id is in the
                         retrieved hits. Denominator: n_cited. Pre-guard.
- fabricated_citation_rate: share of non-abstained answers with at least one
                         citation for which the guard in answer_query found a
                         citation to a chunk_id not passed in the prompt
                         (had_invalid_citation). Denominator: n_cited. The
                         prompt's chunk_ids are the retrieved hits, so this
                         should equal 1 - cited_chunk_retrieved; a difference
                         means the guard and this script disagree on what a
                         citation is.
- uncited_claim_rate:    share of non-abstained answers containing no citation
                         at all. Denominator: n_answered.
- abstain_compliance:    share of abstained queries whose output has no
                         citations and whose answer text is exactly the fixed
                         refusal. Denominator: n_abstain.

A metric is blank where its denominator is 0.

Writes data/results/generation.csv (one row overall, one per answer mode)
and data/results/generation_by_category.csv (one row per category), and
prints both.

Usage: python scripts/evaluate_generation.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import (  # noqa: E402
    RESULTS_DIR, load_profiles, load_queries, print_table, write_csv)
from generate import REFUSAL, answer_query  # noqa: E402
from retrievers import ABSTAIN, ANSWER, ANSWER_CONDITIONALLY  # noqa: E402

GENERATION_OUT = RESULTS_DIR / "generation.csv"
GENERATION_BY_CATEGORY_OUT = RESULTS_DIR / "generation_by_category.csv"
K = 5
MODES = [ANSWER, ANSWER_CONDITIONALLY, ABSTAIN]

CHUNK_ID = re.compile(r"[A-Za-z0-9][\w.-]*::[\w.-]*\w")

METRIC_COLS = ["n_queries", "n_answered", "n_gold", "citation_accuracy",
               "n_cited", "cited_chunk_retrieved", "fabricated_citation_rate",
               "uncited_claim_rate",
               "n_abstain", "abstain_compliance"]


def cited_ids(text):
    """Distinct chunk_id-shaped tokens in text, in first-mention order."""
    return list(dict.fromkeys(CHUNK_ID.findall(text or "")))


def score_query(q, result):
    retrieved = {h["chunk_id"] for h in result["hits"]}
    cited = cited_ids(result["raw_answer_text"])
    abstained = result["mode"] == ABSTAIN
    gold = q["gold_chunk_id"]
    return {
        "query_id": q["query_id"], "category": q["category"], "mode": result["mode"],
        "abstained": abstained,
        "cited": cited,
        "has_gold": bool(gold),
        "gold_cited": bool(gold) and gold in cited,
        "all_cited_retrieved": all(c in retrieved for c in cited),
        "invalid_citations": result["invalid_citations"],
        "had_invalid_citation": result["had_invalid_citation"],
        "flagged": result["flagged"],
        "orphaned_claims": result["orphaned_claims"],
        "abstain_ok": abstained and not cited and not result["citations"]
                      and result["raw_answer_text"] == REFUSAL,
        "cache_hit": result.get("cache_hit"),
    }


def rate(rows, pred):
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else None


def aggregate(rows):
    answered = [r for r in rows if not r["abstained"]]
    with_gold = [r for r in answered if r["has_gold"]]
    with_cites = [r for r in answered if r["cited"]]
    abstained = [r for r in rows if r["abstained"]]
    return {
        "n_queries": len(rows),
        "n_answered": len(answered),
        "n_gold": len(with_gold),
        "citation_accuracy": rate(with_gold, lambda r: r["gold_cited"]),
        "n_cited": len(with_cites),
        "cited_chunk_retrieved": rate(with_cites, lambda r: r["all_cited_retrieved"]),
        "fabricated_citation_rate": rate(with_cites, lambda r: r["had_invalid_citation"]),
        "uncited_claim_rate": rate(answered, lambda r: not r["cited"]),
        "n_abstain": len(abstained),
        "abstain_compliance": rate(abstained, lambda r: r["abstain_ok"]),
    }


def main():
    queries = load_queries()
    profiles = load_profiles()
    print(f"running answer_query over {len(queries)} queries...", file=sys.stderr)
    rows = []
    for i, q in enumerate(queries, 1):
        try:
            result = answer_query(q["question"], profiles[q["asking_user_id"]], K)
        except RuntimeError as e:
            sys.exit(f"error on {q['query_id']}: {e}")
        rows.append(score_query(q, result))
        print(f"  [{i}/{len(queries)}] {q['query_id']} {result['mode']}"
              + ("  (cached)" if result.get("cache_hit") else ""), file=sys.stderr)

    n_llm = sum(1 for r in rows if r["cache_hit"] is not None)
    n_hits = sum(1 for r in rows if r["cache_hit"])
    print(f"LLM responses: {n_llm} ({n_hits} from cache, {n_llm - n_hits} generated)",
          file=sys.stderr)

    overall = [{"group": "overall", **aggregate(rows)}]
    overall += [{"group": f"mode={m}", **aggregate([r for r in rows if r["mode"] == m])}
                for m in MODES]
    categories = sorted({r["category"] for r in rows})
    by_category = [{"category": c, **aggregate([r for r in rows if r["category"] == c])}
                   for c in categories]

    cols = ["group", *METRIC_COLS]
    cat_cols = ["category", *METRIC_COLS]
    write_csv(GENERATION_OUT, overall, cols)
    write_csv(GENERATION_BY_CATEGORY_OUT, by_category, cat_cols)
    print_table(f"Generation ({GENERATION_OUT.relative_to(ROOT)})", overall, cols)
    print_table(f"Generation by category ({GENERATION_BY_CATEGORY_OUT.relative_to(ROOT)})",
                by_category, cat_cols)

    bad = [r for r in rows if r["cited"] and not r["all_cited_retrieved"]]
    if bad:
        print("\nAnswers citing chunk_ids not in the retrieved set:")
        for r in bad:
            print(f"  {r['query_id']} ({r['mode']}): {', '.join(r['cited'])}")
            print(f"    stripped by guard: {', '.join(r['invalid_citations']) or '(none)'}")

    flagged = [r for r in rows if r["flagged"]]
    print(f"\nFlagged answers (stripping left a claim with no citation): {len(flagged)}")
    for r in flagged:
        print(f"  {r['query_id']} ({r['mode']}):")
        for claim in r["orphaned_claims"]:
            print(f"    - {claim}")


if __name__ == "__main__":
    main()
