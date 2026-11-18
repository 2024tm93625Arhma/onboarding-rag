"""Generation layer on top of provenance_answer.

answer_query(query, profile, k) calls retrievers.provenance_answer and passes
the hits it returns to the LLM unchanged: same chunks, same order, no
re-ranking, re-filtering or re-retrieval. The retrieval evaluation in
data/results/ only carries over to generation if the generator sees exactly
the ranked list that was evaluated.

Answer modes:
- abstain:              no LLM call. A fixed refusal pointing to an SME.
- answer:               LLM answers from the top-k chunks, citing [chunk_id].
- answer_conditionally: as answer, and the LLM must also end with a
                        'Condition:' line. The prompt gives exactly one framing:
                        * applicability, if the top-1 has competing versions in
                          the hits (both sides of a declared conflict, or other
                          versions of its policy family): name who the version
                          applies to, from its applies_if;
                        * staleness otherwise (the mode was triggered by the
                          top-1 being below FRESHNESS_FLOOR): a date caveat
                          naming the document's effective_date, with no mention
                          of applicability.

In every mode, each chunk's header is marked [APPLIES TO YOU] (authority ==
AUTHORITY_CURRENT) or [DOES NOT APPLY TO YOU] (superseded or not applicable),
and the system prompt tells the model to answer only from applicable chunks.
The mark comes from the hit's authority; no profile attribute is put in the
prompt.

Providers (stdlib HTTP only, no SDK dependencies), chosen by LLM_PROVIDER:
- anthropic: ANTHROPIC_API_KEY; model LLM_MODEL (default claude-opus-5-5)
- openai:    OPENAI_API_KEY, optional OPENAI_BASE_URL; model LLM_MODEL (required)
- azure:     AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
             optional AZURE_OPENAI_API_VERSION; the deployment is the model
- ollama:    optional OLLAMA_HOST (default http://localhost:11434); model
             LLM_MODEL (required)
All calls use temperature 0.

Citation format, chosen by CITATION_FORMAT (env var of the same name):
- chunk_id (default): each chunk is headed [<chunk_id>] and the model cites
  chunk_ids.
- numbered: each chunk is headed [1], [2], ... in rank order (the marking is
  kept) and the model cites by number. answer_query maps every bracketed
  number back to its chunk_id before anything else sees the text, so
  raw_answer_text, the guard and all metrics work on chunk_ids exactly as
  under chunk_id. A number outside 1..len(hits) becomes the chunk_id-shaped
  token out-of-range::<n>, which is not in the prompt, so the guard strips it
  as an invalid citation and the evaluator counts it as fabricated.
  model_answer_text keeps the model's numbered text.

Citation guard: after the model returns, every cited chunk_id is checked
against the chunk_ids passed in the prompt. Any not in that set is stripped
from answer_text and recorded in invalid_citations (had_invalid_citation is
set). If that leaves a claim (a sentence or list item) with no citation, the
answer is flagged (flagged, orphaned_claims) instead of being returned as if
it were fully cited. The cache stores the raw response; the guard runs on
every call, cached or not.

Every LLM response is cached in data/generation_cache/<sha256>.json, keyed
by (provider, model, query, profile_id, chunk_ids, prompt), plus
citation_format when it is not chunk_id (the chunk_id key is left as it was,
so existing cache entries stay valid). A re-run with the same inputs reads the
cache and makes no network call.

CLI:
    python -m src.generate "<query>" --profile u001 [--k 5]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from provenance import load_profiles, policy_family  # noqa: E402
from retrievers import (  # noqa: E402
    ABSTAIN, ANSWER, ANSWER_CONDITIONALLY, AUTHORITY_CURRENT, conflict_pairs,
    provenance_answer)

CACHE_DIR = ROOT / "data" / "generation_cache"
TEMPERATURE = 0
MAX_TOKENS = 1024
TIMEOUT = 300  # seconds per HTTP call

CITATION_FORMATS = ("chunk_id", "numbered")
CITATION_FORMAT = os.environ.get("CITATION_FORMAT", "chunk_id").strip().lower()
if CITATION_FORMAT not in CITATION_FORMATS:
    raise RuntimeError(f"unknown CITATION_FORMAT {CITATION_FORMAT!r}; expected one of: "
                       + ", ".join(CITATION_FORMATS))

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
    "4. Be concise.\n"
    "5. Each chunk header is marked [APPLIES TO YOU] or [DOES NOT APPLY TO YOU]. "
    "Answer from the chunks marked [APPLIES TO YOU]. Chunks marked "
    "[DOES NOT APPLY TO YOU] are shown only for context and must not be used as "
    "the answer. Do not present values from a version that does not apply as an "
    "alternative or option for the user.")

_CHUNK_ID_CITE_RULE = (
    "2. Cite every claim with the chunk_id it comes from, in square brackets, "
    "e.g. [hr-leave-policy-v2::s03p0]. Use only chunk_ids that appear below.\n")
_NUMBERED_CITE_RULE = (
    "2. Cite every claim with the number of the chunk it comes from, in square "
    "brackets, e.g. [2]. Use only chunk numbers that appear below.\n")
assert _CHUNK_ID_CITE_RULE in SYSTEM_PROMPT
SYSTEM_PROMPTS = {
    "chunk_id": SYSTEM_PROMPT,
    "numbered": SYSTEM_PROMPT.replace(_CHUNK_ID_CITE_RULE, _NUMBERED_CITE_RULE),
}
ANSWER_CUES = {
    "chunk_id": "\nAnswer (cite every claim as [chunk_id]):",
    "numbered": "\nAnswer (cite every claim as [chunk number]):",
}

APPLIES_MARK = "[APPLIES TO YOU]"
NOT_APPLIES_MARK = "[DOES NOT APPLY TO YOU]"


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

def cache_key(provider, model, query, profile_id, chunk_ids, prompt,
              citation_format="chunk_id"):
    parts = [provider, model, query, profile_id, list(chunk_ids), prompt]
    if citation_format != "chunk_id":  # chunk_id keeps the original key
        parts.append(citation_format)
    blob = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cached_call(provider, model, call, query, profile_id, chunk_ids, system, user,
                citation_format="chunk_id"):
    """(response text, cache_hit)."""
    prompt = {"system": system, "user": user}
    key = cache_key(provider, model, query, profile_id, chunk_ids, prompt, citation_format)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return json.load(f)["response"], True
    response = call(system, user, model)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"provider": provider, "model": model, "query": query,
              "profile_id": profile_id, "chunk_ids": list(chunk_ids),
              "temperature": TEMPERATURE, "citation_format": citation_format,
              "prompt": prompt, "response": response}
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


def competing_docs(hits):
    """{doc_id: hit} of the top-1's doc and its competing versions in hits.

    Competing versions are (a) both sides of any declared-conflict pair among
    the hits and (b) other docs in the hits from the top-1's policy family.
    The top-1's doc comes first.
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
    return docs


def conditional_framing(hits):
    """'applicability' when the top-1 has competing versions in hits, else
    'staleness'. Exactly one framing is ever given to the model."""
    return "applicability" if len(competing_docs(hits)) > 1 else "staleness"


def applicability_instruction(hits):
    """Prompt block asking for a condition naming who the version applies to."""
    docs = competing_docs(hits)
    top_id = hits[0]["metadata"]["doc_id"]
    lines = []
    for doc_id, hit in docs.items():
        role = "source of the answer" if doc_id == top_id else "competing version"
        lines.append(f"- {doc_id} ({role}): applies if {_describe_applies_if(hit)}")
    others = [d for d in docs if d != top_id]
    lines.append(f"- {top_id} takes precedence over {', '.join(others)}, which may "
                 "state a different value.")
    return (
        "\nOther versions of this policy exist and may apply to different people. "
        "The versions and who each applies to:\n"
        + "\n".join(lines) + "\n"
        "Answer the question from the source of the answer, then end with one line "
        "starting 'Condition:' that names who this version applies to, taken from "
        "its 'applies if' above.\n")


def staleness_instruction(hits):
    """Prompt block asking ONLY for a date-based caveat on the top-1's age."""
    top = hits[0]
    top_id = top["metadata"]["doc_id"]
    date = top["metadata"]["effective_date"]
    return (
        f"\nThe source of this answer, {top_id}, took effect on {date} and may be "
        "out of date.\n"
        "Answer the question, then end with one line starting 'Condition:' that "
        f"says the answer is based on {top_id}, effective {date}, and may be out "
        "of date. Do not claim the document is current or the latest version.\n")


def applicability_mark(hit):
    """Header mark from the hit's authority for the asking user.

    Only AUTHORITY_CURRENT applies: a superseded version (a later version also
    applies to the user) and a non-applicable one are both marked as not
    applying. The mark is derived from authority alone, so no profile
    attribute reaches the prompt.
    """
    return APPLIES_MARK if applies_to_user(hit) else NOT_APPLIES_MARK


def applies_to_user(hit):
    """True iff the hit is marked [APPLIES TO YOU] in the prompt."""
    return hit["authority"] == AUTHORITY_CURRENT


def build_prompt(query, hits, mode, citation_format=CITATION_FORMAT):
    """(system, user). Chunks appear in exactly the order of hits, each header
    marked with whether it applies to the asking user. The header label is the
    chunk_id, or under citation_format "numbered" the 1-based rank."""
    def label(i, h):
        return str(i) if citation_format == "numbered" else h["chunk_id"]
    blocks = "\n\n".join(f"[{label(i, h)}] {applicability_mark(h)}\n{h['chunk_body']}"
                         for i, h in enumerate(hits, 1))
    user = f"Chunks:\n\n{blocks}\n\nQuestion: {query}\n"
    if mode == ANSWER_CONDITIONALLY:
        if conditional_framing(hits) == "applicability":
            user += applicability_instruction(hits)
        else:
            user += staleness_instruction(hits)
    user += ANSWER_CUES[citation_format]
    return SYSTEM_PROMPTS[citation_format], user


# A bracket group of chunk numbers: [2], [1, 3], [1; 3].
NUMBER_GROUP_RE = re.compile(r"\[\s*(\d+(?:\s*[,;]\s*\d+)*)\s*\]")


def numbers_to_chunk_ids(text, chunk_ids):
    """Rewrite numbered citations as chunk_id citations: [n] -> [chunk_ids[n-1]].
    A number outside 1..len(chunk_ids) becomes [out-of-range::n], which is not
    in the prompt, so the guard strips it as an invalid citation."""
    def one(n):
        n = int(n)
        return chunk_ids[n - 1] if 1 <= n <= len(chunk_ids) else f"out-of-range::{n}"
    return NUMBER_GROUP_RE.sub(
        lambda m: "[" + ", ".join(one(n) for n in re.split(r"\s*[,;]\s*", m.group(1))) + "]",
        text)


# -------------------------------------------------------------------- answer

def extract_citations(text, allowed_ids):
    """chunk_ids cited in text, in first-mention order, restricted to allowed_ids."""
    cited = []
    for cid in allowed_ids:
        pos = text.find(f"[{cid}]")
        if pos >= 0:
            cited.append((pos, cid))
    return [cid for _, cid in sorted(cited)]


# Any chunk_id-shaped token (<doc_id>::<chunk>), bracketed or bare. Same
# pattern as scripts/evaluate_generation.py, so the guard and the evaluator
# agree on what counts as a citation.
CHUNK_ID_RE = re.compile(r"[A-Za-z0-9][\w.-]*::[\w.-]*\w")
# A bracket group holding one or more chunk_ids, e.g. [a::s01p0] or [a::s01p0, b::s02p0].
CITATION_GROUP_RE = re.compile(r"\[([^\[\]\n]*::[^\[\]\n]*)\]")
# Claims are lines, split further into sentences. A segment that is only
# citations (e.g. "Submit the form. [x]") is joined to the sentence before it.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CITATION_ONLY_RE = re.compile(r"^(\[[^\[\]]*\][\s.,;:]*)+$")
_REMOVED = "\x00"


def split_claims(text):
    """Claim segments of text: non-empty lines, each split into sentences."""
    claims = []
    for line in text.splitlines():
        segments = []
        for seg in _SENTENCE_SPLIT_RE.split(line.strip()):
            if not seg:
                continue
            if segments and _CITATION_ONLY_RE.match(seg):
                segments[-1] += " " + seg
            else:
                segments.append(seg)
        claims.extend(segments)
    return claims


def validate_citations(text, allowed_ids):
    """(clean_text, invalid_citations, orphaned_claims).

    Every chunk_id cited in text that is not in allowed_ids (the chunk_ids
    passed in the prompt) is stripped from the text. invalid_citations lists
    the distinct stripped ids in first-mention order. orphaned_claims lists
    the claims (from the original text) that cited only invalid ids, so
    after stripping they have no citation at all.
    """
    allowed = set(allowed_ids)
    invalid = list(dict.fromkeys(c for c in CHUNK_ID_RE.findall(text) if c not in allowed))
    if not invalid:
        return text, [], []

    def fix_group(m):
        ids = CHUNK_ID_RE.findall(m.group(1))
        keep = [c for c in ids if c in allowed]
        if len(keep) == len(ids):
            return m.group(0)
        return f"[{', '.join(keep)}]" if keep else _REMOVED

    clean = CITATION_GROUP_RE.sub(fix_group, text)
    # Bare (unbracketed) invalid ids left after the bracket pass.
    clean = CHUNK_ID_RE.sub(lambda m: m.group(0) if m.group(0) in allowed else _REMOVED,
                            clean)
    # Drop each removal mark with the space before it, and with the separator
    # joining it to a kept citation group ("[a], [b]" -> "[a]").
    clean = re.sub(r"(?<=\])[ \t]*[,;][ \t]*" + _REMOVED, "", clean)
    clean = re.sub(_REMOVED + r"[ \t]*[,;][ \t]*(?=\[)", "", clean)
    clean = re.sub(r"[ \t]*" + _REMOVED, "", clean)

    orphaned = []
    for claim in split_claims(text):
        ids = CHUNK_ID_RE.findall(claim)
        if ids and not any(c in allowed for c in ids):
            orphaned.append(claim)
    return clean, invalid, orphaned


def answer_query(query, profile, k=5, citation_format=None):
    """{mode, answer_text, raw_answer_text, citations, invalid_citations,
    had_invalid_citation, orphaned_claims, flagged, hits, relevance}.

    hits is provenance_answer's list, unchanged. answer_text is the model's
    answer with every citation to a chunk_id not passed in the prompt removed;
    raw_answer_text is the model's answer before that. invalid_citations
    lists the removed chunk_ids. citations are the chunk_ids from hits that
    the answer cites (empty for abstain). flagged is True when stripping left
    a claim with no citation at all; orphaned_claims lists those claims as the
    model wrote them. applicability maps each chunk_id that went into the
    prompt to True ([APPLIES TO YOU]) or False ([DOES NOT APPLY TO YOU]);
    it is empty for abstain, where no prompt is built. model_answer_text is
    the model's text as returned; under citation_format "numbered" it holds
    [n] citations, and raw_answer_text is the same text with each number
    mapped back to its chunk_id (numbers_to_chunk_ids).
    """
    citation_format = citation_format or CITATION_FORMAT
    if citation_format not in CITATION_FORMATS:
        raise RuntimeError(f"unknown citation_format {citation_format!r}")
    mode, hits, relevance = provenance_answer(query, profile, k)
    result = {"mode": mode, "answer_text": None, "raw_answer_text": None,
              "model_answer_text": None, "citation_format": citation_format,
              "citations": [], "invalid_citations": [], "had_invalid_citation": False,
              "orphaned_claims": [], "flagged": False, "applicability": {},
              "hits": hits, "relevance": relevance}
    if mode == ABSTAIN:
        result["answer_text"] = result["raw_answer_text"] = REFUSAL
        result["model_answer_text"] = REFUSAL
        return result
    assert mode in (ANSWER, ANSWER_CONDITIONALLY), mode
    provider, model, call = resolve_provider()
    chunk_ids = [h["chunk_id"] for h in hits]
    system, user = build_prompt(query, hits, mode, citation_format)
    text, cache_hit = cached_call(provider, model, call, query, profile["user_id"],
                                  chunk_ids, system, user, citation_format)
    model_text = text.strip()
    raw = (numbers_to_chunk_ids(model_text, chunk_ids) if citation_format == "numbered"
           else model_text)
    clean, invalid, orphaned = validate_citations(raw, chunk_ids)
    result.update(answer_text=clean, raw_answer_text=raw, model_answer_text=model_text,
                  citations=extract_citations(clean, chunk_ids),
                  invalid_citations=invalid, had_invalid_citation=bool(invalid),
                  orphaned_claims=orphaned, flagged=bool(orphaned),
                  applicability={h["chunk_id"]: applies_to_user(h) for h in hits},
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
    if result["had_invalid_citation"]:
        print(f"invalid citations stripped: {', '.join(result['invalid_citations'])}")
    if result["flagged"]:
        print("\nWARNING: stripping invalid citations left these claims with no citation:")
        for claim in result["orphaned_claims"]:
            print(f"  - {claim}")


if __name__ == "__main__":
    main()
