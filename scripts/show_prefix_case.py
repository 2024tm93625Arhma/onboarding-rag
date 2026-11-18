import sys, json
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path[:0] = [str(ROOT/"src"), str(ROOT/"scripts")]
import generate
from score_preapplicability import pre_fix_result
from evaluate import load_profiles, load_queries
def no_net(*a, **k): raise SystemExit("cache miss - refusing to call the LLM")
for p in list(generate.PROVIDERS): generate.PROVIDERS[p] = no_net
provider, model, _ = generate.resolve_provider()
profiles = load_profiles()
for q in load_queries():
    prof = profiles[q["asking_user_id"]]
    pre = pre_fix_result(q["question"], prof, provider, model)
    if pre is None or pre["mode"] == "abstain": continue
    bad = [c for c in pre["citations"] if pre["applicability"].get(c) is False]
    if not bad: continue
    post = generate.answer_query(q["question"], prof, 5, citation_format="chunk_id")
    num = generate.answer_query(q["question"], prof, 5, citation_format="numbered")
    print("="*78); print(f"{q['query_id']} [{q['category']}] mode={pre['mode']}")
    print("Query:", q["question"]); print("Gold:", q.get("gold_chunk_id"))
    print("Profile:", json.dumps(prof, ensure_ascii=False))
    print("\nTop-5 hits (rank, chunk_id, authority, applies_if):")
    for i, h in enumerate(pre["hits"], 1):
        md = h["metadata"]
        print(f"  {i}. {h['chunk_id']}  authority={h['authority']}  status={md.get('status')}"
              f"  effective={md.get('effective_date')}  applies_if={generate._describe_applies_if(h)}")
    for c in bad:
        h = next(h for h in pre["hits"] if h["chunk_id"] == c)
        print(f"\nInapplicable chunk cited: {c}\n--- body ---\n{h['chunk_body']}\n------------")
    print("\nPRE-FIX answer (raw):\n" + pre["raw_answer_text"])
    print("\nPOST-FIX answer, chunk_id (raw):\n" + post["raw_answer_text"], "\n  citations:", post["citations"], "cache_hit:", post.get("cache_hit"))
    print("\nPOST-FIX answer, numbered (mapped):\n" + num["raw_answer_text"], "\n  citations:", num["citations"], "cache_hit:", num.get("cache_hit"))
