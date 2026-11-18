"""Score the pre-applicability generation run with the applicability metrics.

Before applicability was passed into the prompt, chunk headers were plain
[<chunk_id>] and the system prompt had no rule 5. Those answers are still in
data/generation_cache/. This script rebuilds each pre-fix prompt exactly (same
hits from provenance_answer, same conditional framing, pre-fix system prompt,
headers and answer cue), looks up the cached response by its cache key, runs
the citation guard on it as answer_query does, and scores it with
scripts/evaluate_generation.py.

Applicability is a property of the chunk and the user profile, not of the
prompt, so each prompt chunk is given the marking it would have had under the
current build_prompt (generate.applies_to_user); the pre-fix model simply never
saw it.

It makes no LLM calls: a query whose pre-fix answer is not in the cache is
reported and excluded from every count.

Every existing column of data/results/generation_preapplicability.csv and
generation_by_category_preapplicability.csv is recomputed and must match the
file exactly; on any mismatch the script exits without writing. Otherwise the
applicability columns are appended and the existing values are left as they
were.

Usage: LLM_PROVIDER=ollama LLM_MODEL=llama3 python scripts/score_preapplicability.py
       (provider and model only select the cache entries; nothing is called)
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
from evaluate import RESULTS_DIR, fmt, load_profiles, load_queries, write_csv  # noqa: E402
from evaluate_generation import K, METRIC_COLS, MODES, aggregate, score_query  # noqa: E402
from retrievers import ABSTAIN, ANSWER_CONDITIONALLY, provenance_answer  # noqa: E402

OVERALL_OUT = RESULTS_DIR / "generation_preapplicability.csv"
BY_CATEGORY_OUT = RESULTS_DIR / "generation_by_category_preapplicability.csv"

# Pre-fix prompt pieces: the current ones minus the applicability rule.
_RULE_5 = "\n5. Each chunk header is marked [APPLIES TO YOU]"
PRE_FIX_SYSTEM = generate.SYSTEM_PROMPT[:generate.SYSTEM_PROMPT.index(_RULE_5)]
assert PRE_FIX_SYSTEM.endswith("4. Be concise."), PRE_FIX_SYSTEM
PRE_FIX_CUE = generate.ANSWER_CUES["chunk_id"]


def pre_fix_prompt(query, hits, mode):
    """(system, user) exactly as build_prompt produced them before applicability."""
    blocks = "\n\n".join(f"[{h['chunk_id']}]\n{h['chunk_body']}" for h in hits)
    user = f"Chunks:\n\n{blocks}\n\nQuestion: {query}\n"
    if mode == ANSWER_CONDITIONALLY:
        if generate.conditional_framing(hits) == "applicability":
            user += generate.applicability_instruction(hits)
        else:
            user += generate.staleness_instruction(hits)
    user += PRE_FIX_CUE
    return PRE_FIX_SYSTEM, user


def pre_fix_result(query, profile, provider, model):
    """answer_query's result for the pre-fix cached answer, or None if not cached."""
    mode, hits, relevance = provenance_answer(query, profile, K)
    result = {"mode": mode, "answer_text": None, "raw_answer_text": None,
              "citations": [], "invalid_citations": [], "had_invalid_citation": False,
              "orphaned_claims": [], "flagged": False, "applicability": {},
              "hits": hits, "relevance": relevance}
    if mode == ABSTAIN:
        result["answer_text"] = result["raw_answer_text"] = generate.REFUSAL
        return result
    chunk_ids = [h["chunk_id"] for h in hits]
    system, user = pre_fix_prompt(query, hits, mode)
    key = generate.cache_key(provider, model, query, profile["user_id"], chunk_ids,
                             {"system": system, "user": user})
    path = generate.CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)["response"].strip()
    clean, invalid, orphaned = generate.validate_citations(raw, chunk_ids)
    result.update(answer_text=clean, raw_answer_text=raw,
                  citations=generate.extract_citations(clean, chunk_ids),
                  invalid_citations=invalid, had_invalid_citation=bool(invalid),
                  orphaned_claims=orphaned, flagged=bool(orphaned),
                  applicability={h["chunk_id"]: generate.applies_to_user(h) for h in hits},
                  cache_hit=True)
    return result


def merge(path, key_col, new_rows):
    """Existing rows of path with new columns appended; exits on any mismatch."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        old_cols, old_rows = reader.fieldnames, list(reader)
    new_by_key = {r[key_col]: r for r in new_rows}
    if [r[key_col] for r in old_rows] != [r[key_col] for r in new_rows]:
        sys.exit(f"{path.name}: row keys differ from the recomputation; nothing written")
    mismatches = [(r[key_col], c, r[c], fmt(new_by_key[r[key_col]][c]))
                  for r in old_rows for c in old_cols if c != key_col
                  and r[c] != fmt(new_by_key[r[key_col]][c])]
    if mismatches:
        print(f"{path.name}: recomputed values differ from the committed file:",
              file=sys.stderr)
        for k, c, old, new in mismatches:
            print(f"  {k} {c}: file={old!r} recomputed={new!r}", file=sys.stderr)
        sys.exit("nothing written")
    added = [c for c in METRIC_COLS if c not in old_cols]
    merged = [{**r, **{c: new_by_key[r[key_col]][c] for c in added}} for r in old_rows]
    return merged, [*old_cols, *added]


def main():
    provider, model, _ = generate.resolve_provider()  # selects cache entries only
    queries = load_queries()
    profiles = load_profiles()
    rows, missing = [], []
    for q in queries:
        result = pre_fix_result(q["question"], profiles[q["asking_user_id"]],
                                provider, model)
        if result is None:
            missing.append(q["query_id"])
            continue
        rows.append(score_query(q, result))
    answered = sum(1 for r in rows if not r["abstained"])
    print(f"pre-fix answers found in cache: {answered}; missing (excluded): "
          f"{len(missing)}{' ' + ', '.join(missing) if missing else ''}", file=sys.stderr)

    overall = [{"group": "overall", **aggregate(rows)}]
    overall += [{"group": f"mode={m}", **aggregate([r for r in rows if r["mode"] == m])}
                for m in MODES]
    categories = sorted({r["category"] for r in rows})
    by_category = [{"category": c, **aggregate([r for r in rows if r["category"] == c])}
                   for c in categories]

    # Check both files before writing either.
    overall_rows, overall_cols = merge(OVERALL_OUT, "group", overall)
    cat_rows, cat_cols = merge(BY_CATEGORY_OUT, "category", by_category)
    write_csv(OVERALL_OUT, overall_rows, overall_cols)
    write_csv(BY_CATEGORY_OUT, cat_rows, cat_cols)
    print(f"existing values reproduced exactly; appended to {OVERALL_OUT.name} and "
          f"{BY_CATEGORY_OUT.name}", file=sys.stderr)

    print("\nPer-query (pre-fix, answered queries citing an inapplicable chunk):")
    for r in rows:
        if r["inapplicable_cited"]:
            bad = [c for c in r["surviving_cited"] if r["applicability"].get(c) is False]
            print(f"  {r['query_id']} ({r['category']}, {r['mode']}): {', '.join(bad)}")


if __name__ == "__main__":
    main()
