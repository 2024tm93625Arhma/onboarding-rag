"""Generation layer on top of provenance_answer.

answer_query(query, profile, k) calls retrievers.provenance_answer and passes
the hits it returns to the LLM unchanged: same chunks, same order, no
re-ranking, re-filtering or re-retrieval. The retrieval evaluation in
data/results/ only carries over to generation if the generator sees exactly
the ranked list that was evaluated.

Answer modes:
- abstain:              no LLM call. A fixed refusal pointing to an SME.
- answer:               LLM answers from the top-k chunks, citing [chunk_id].
- answer_conditionally: as answer, and the LLM must also state the condition
                        under which the answer holds. The condition is built
                        from the applies_if of the competing versions in the
                        hits (both sides of a declared conflict, and other
                        versions of the top-1's policy family) and, when the
                        top-1 is below FRESHNESS_FLOOR, from its
                        effective_date.

Providers (stdlib HTTP only, no SDK dependencies), chosen by LLM_PROVIDER:
- anthropic: ANTHROPIC_API_KEY; model LLM_MODEL (default claude-opus-5-5)
- openai:    OPENAI_API_KEY, optional OPENAI_BASE_URL; model LLM_MODEL (required)
- azure:     AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
             optional AZURE_OPENAI_API_VERSION; the deployment is the model
- ollama:    optional OLLAMA_HOST (default http://localhost:11434); model
             LLM_MODEL (required)
All calls use temperature 0.

Every LLM response is cached in data/generation_cache/<sha256>.json, keyed
by (provider, model, query, profile_id, chunk_ids, prompt). A re-run with the
same inputs reads the cache and makes no network call.

CLI:
    python -m src.generate "<query>" --profile u001 [--k 5]
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from provenance import load_profiles, policy_family  # noqa: E402
from retrievers import (  # noqa: E402
    ABSTAIN, ANSWER, ANSWER_CONDITIONALLY, FRESHNESS_FLOOR, conflict_pairs,
    provenance_answer)

CACHE_DIR = ROOT / "data" / "generation_cache"
TEMPERATURE = 0
MAX_TOKENS = 1024
TIMEOUT = 300  # seconds per HTTP call

REFUSAL = ("I can't answer this reliably from the documents available to you. "
           "Please raise it with a subject-matter expert (SME) in the owning team, "
           "or with your manager, who can confirm the correct policy for your situation.")

SYSTEM_PROMPT = (
    "You are an onboarding assistant answering an employee's question from "
    "company policy documents.\n"
    "Rules:\n"
    "1. Answer ONLY from the chunks provided below. Do not use outside knowledge.\n"
    "2. Cite every claim with the chunk_id it comes from, in square brackets, "
    "e.g. [hr-leave-policy-v2::s03p0]. Use only chunk_ids that appear below.\n"
    "3. If the chunks do not contain the answer, say that you cannot answer "
    "from the provided documents, and do not guess.\n"
    "4. Be concise.")


# ------------------------------------------------------------------ providers
# Each provider: (system, user, model) -> response text.

def _post_json(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request to {url} failed: HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM request to {url} failed: {e.reason}") from None


def _env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        raise RuntimeError(f"environment variable {name} is not set "
                           f"(needed for LLM_PROVIDER={os.environ.get('LLM_PROVIDER')})")
    return value


def call_anthropic(system, user, model):
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"model": model, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
         "system": system, "messages": [{"role": "user", "content": user}]},
        {"x-api-key": _env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


def call_openai(system, user, model):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data = _post_json(
        f"{base}/chat/completions",
        {"model": model, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {"Authorization": f"Bearer {_env('OPENAI_API_KEY')}"})
    return data["choices"][0]["message"]["content"]


def call_azure(system, user, model):
    endpoint = _env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01")
    data = _post_json(
        f"{endpoint}/openai/deployments/{model}/chat/completions?api-version={version}",
        {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {"api-key": _env("AZURE_OPENAI_API_KEY")})
    return data["choices"][0]["message"]["content"]


def call_ollama(system, user, model):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    if not host.startswith("http"):
        host = f"http://{host}"
    data = _post_json(
        f"{host}/api/chat",
        {"model": model, "stream": False,
         "options": {"temperature": TEMPERATURE, "seed": 0},
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {})
    return data["message"]["content"]


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "azure": call_azure,
    "ollama": call_ollama,
}

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}


def resolve_provider():
    """(provider name, model, call function) from the environment."""
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if not provider:
        raise RuntimeError(
            "LLM_PROVIDER is not set. Set it to one of: " + ", ".join(PROVIDERS)
            + " (plus that provider's API key / endpoint variables; see src/generate.py).")
    if provider not in PROVIDERS:
        raise RuntimeError(f"unknown LLM_PROVIDER {provider!r}; expected one of: "
                           + ", ".join(PROVIDERS))
    if provider == "azure":
        model = _env("AZURE_OPENAI_DEPLOYMENT")
    else:
        model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider)
        if not model:
            raise RuntimeError(f"LLM_MODEL is not set (required for LLM_PROVIDER={provider})")
    return provider, model, PROVIDERS[provider]


# ---------------------------------------------------------------------- cache

def cache_key(provider, model, query, profile_id, chunk_ids, prompt):
    blob = json.dumps([provider, model, query, profile_id, list(chunk_ids), prompt],
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cached_call(provider, model, call, query, profile_id, chunk_ids, system, user):
    """(response text, cache_hit)."""
    prompt = {"system": system, "user": user}
    key = cache_key(provider, model, query, profile_id, chunk_ids, prompt)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)["response"], True
    response = call(system, user, model)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"provider": provider, "model": model, "query": query,
              "profile_id": profile_id, "chunk_ids": list(chunk_ids),
              "temperature": TEMPERATURE, "prompt": prompt, "response": response}
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return response, False


# --------------------------------------------------------------------- prompt

def _format_condition(cond):
    return f"{cond['field']} {cond['op']} {cond['value']}"


def _describe_applies_if(hit):
    conds = hit["metadata"].get("applies_if") or []
    return " AND ".join(_format_condition(c) for c in conds) if conds else "no condition (everyone)"


def competing_conditions(hits):
    """Lines describing when the top-1 answer holds, from the hits only.

    Competing versions are (a) both sides of any declared-conflict pair among
    the hits and (b) other docs in the hits from the top-1's policy family.
    If the top-1 is below FRESHNESS_FLOOR its effective_date is added.
    """
    top = hits[0]
    docs = {top["metadata"]["doc_id"]: top}
    for a, b, _ in conflict_pairs(hits):
        docs.setdefault(a["metadata"]["doc_id"], a)
        docs.setdefault(b["metadata"]["doc_id"], b)
    family = policy_family(top)
    for hit in hits:
        if policy_family(hit) == family:
            docs.setdefault(hit["metadata"]["doc_id"], hit)
    top_id = top["metadata"]["doc_id"]
    lines = []
    for doc_id, hit in docs.items():
        role = "source of the answer" if doc_id == top_id else "competing version"
        lines.append(f"- {doc_id} ({role}, effective {hit['metadata']['effective_date']}): "
                     f"applies if {_describe_applies_if(hit)}")
    others = [d for d in docs if d != top_id]
    if others:
        lines.append(f"- {top_id} takes precedence over {', '.join(others)}, which may "
                     "state a different value; the answer holds only if that precedence "
                     "is correct for the user.")
    if top.get("freshness", 1.0) < FRESHNESS_FLOOR:
        lines.append(f"- {top_id} took effect on {top['metadata']['effective_date']} "
                     "and may be out of date; the answer holds only if it is still current.")
    return lines


def build_prompt(query, hits, mode):
    """(system, user). Chunks appear in exactly the order of hits."""
    blocks = "\n\n".join(f"[{h['chunk_id']}]\n{h['chunk_body']}" for h in hits)
    user = f"Chunks:\n\n{blocks}\n\nQuestion: {query}\n"
    if mode == ANSWER_CONDITIONALLY:
        conditions = "\n".join(competing_conditions(hits))
        user += (
            "\nThis answer only holds under certain conditions. Competing versions "
            "and their applicability conditions:\n"
            f"{conditions}\n"
            "Answer the question, then end with one line starting 'Condition:' "
            "that states when your answer holds, taken from the conditions above "
            "(who the version applies to, which document it overrides, or that the "
            "document may be out of date, with its date).\n")
    user += "\nAnswer (cite every claim as [chunk_id]):"
    return SYSTEM_PROMPT, user


# -------------------------------------------------------------------- answer

def extract_citations(text, allowed_ids):
    """chunk_ids cited in text, in first-mention order, restricted to allowed_ids."""
    cited = []
    for cid in allowed_ids:
        pos = text.find(f"[{cid}]")
        if pos >= 0:
            cited.append((pos, cid))
    return [cid for _, cid in sorted(cited)]


def answer_query(query, profile, k=5):
    """{mode, answer_text, citations, hits, relevance}.

    hits is provenance_answer's list, unchanged. citations are the chunk_ids
    from hits that the answer cites (empty for abstain).
    """
    mode, hits, relevance = provenance_answer(query, profile, k)
    result = {"mode": mode, "answer_text": None, "citations": [],
              "hits": hits, "relevance": relevance}
    if mode == ABSTAIN:
        result["answer_text"] = REFUSAL
        return result
    assert mode in (ANSWER, ANSWER_CONDITIONALLY), mode
    provider, model, call = resolve_provider()
    chunk_ids = [h["chunk_id"] for h in hits]
    system, user = build_prompt(query, hits, mode)
    text, cache_hit = cached_call(provider, model, call, query, profile["user_id"],
                                  chunk_ids, system, user)
    result.update(answer_text=text.strip(),
                  citations=extract_citations(text, chunk_ids),
                  provider=provider, model=model, cache_hit=cache_hit)
    return result


def main():
    parser = argparse.ArgumentParser(description="Answer a query with citations.")
    parser.add_argument("query")
    parser.add_argument("--profile", required=True, help="user_id, e.g. u001")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    profiles = load_profiles()
    if args.profile not in profiles:
        parser.error(f"unknown profile {args.profile!r}; known: {', '.join(profiles)}")
    try:
        result = answer_query(args.query, profiles[args.profile], args.k)
    except RuntimeError as e:
        sys.exit(f"error: {e}")
    relevance = result["relevance"]
    print(f"query:     {args.query}")
    print(f"profile:   {args.profile}")
    print(f"mode:      {result['mode']}"
          + (f"  (top-1 relevance {relevance:.3f})" if relevance is not None else ""))
    if "provider" in result:
        print(f"model:     {result['provider']}/{result['model']}"
              f"{'  (cached)' if result['cache_hit'] else ''}")
    print(f"retrieved: {', '.join(h['chunk_id'] for h in result['hits']) or '(none)'}")
    print(f"\nanswer:\n{result['answer_text']}\n")
    print(f"citations: {', '.join(result['citations']) or '(none)'}")


if __name__ == "__main__":
    main()
