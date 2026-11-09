"""HTTP API over the existing pipeline (FastAPI).

Endpoints:
- POST /ask       answer a question for a given user profile, via
                  generate.answer_query(), called unchanged.
- GET  /profiles  the user profiles a caller can ask as.
- GET  /health    liveness, configured LLM provider, and indexed chunk count.

The chunk store, the Chroma collection, the embedding model, the
cross-encoder and the user profiles are loaded ONCE at startup (lifespan
handler), not per request. Retrieval, generation and their parameters are
exactly those in src/retrievers.py and src/generate.py; this module adds no
re-ranking, filtering or post-processing beyond reshaping the result.

SECURITY / SCOPE BOUNDARY: user_id is supplied by the caller and is NOT
authenticated. Scope filtering (department_scope, applies_if, sensitivity)
is enforced against whichever profile the caller names, so anyone who can
reach this API can ask as any user. In a real deployment the identity must
come from the enterprise identity provider (e.g. an OIDC/SAML token
validated by the gateway), never from the request body. This is a
deliberate scope boundary of the dissertation, not an oversight: the
contribution evaluated here is provenance-aware retrieval and generation
given a trusted profile, not authentication.

Run:
    uvicorn src.api:app --port 8000
LLM_PROVIDER (and that provider's variables, see src/generate.py) must be set
for /ask to generate answers; /health and /profiles work without it, and
abstain-mode answers need no LLM call.
"""

import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retrievers  # noqa: E402
from generate import answer_query  # noqa: E402
from provenance import load_profiles  # noqa: E402

PROFILE_FIELDS = ("user_id", "department", "grade", "location",
                  "employment_type", "join_date")

AUTH_NOTE = (
    "**user_id is supplied by the caller and is NOT authenticated.** Scope "
    "filtering is enforced against the profile named here, so in a real "
    "deployment the identity must come from the enterprise identity provider, "
    "not the request body. This is a deliberate scope boundary of the "
    "dissertation, not an oversight.")


@asynccontextmanager
async def lifespan(app):
    """Load index, models and profiles once, before serving requests."""
    t0 = time.perf_counter()
    load_profiles()
    retrievers._chunks()
    retrievers._chunks_by_id()
    retrievers._family_versions()
    retrievers._collection()
    retrievers._embedder()
    retrievers._cross_encoder()
    app.state.startup_seconds = time.perf_counter() - t0
    print(f"api: loaded {len(retrievers._chunks())} chunks, "
          f"{len(load_profiles())} profiles and models in "
          f"{app.state.startup_seconds:.1f}s", flush=True)
    yield


app = FastAPI(title="Onboarding RAG", lifespan=lifespan,
              description="Provenance-aware onboarding Q&A.\n\n" + AUTH_NOTE)


# --------------------------------------------------------------------- models

class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    user_id: str = Field(description="Caller-supplied, NOT authenticated.")
    k: int = Field(5, ge=1, le=20)


class Hit(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    version: str | int | None
    effective_date: str | None
    authority: float
    score: float


class AskResponse(BaseModel):
    mode: str
    answer: str
    citations: list[str]
    invalid_citations: list[str]
    flagged: bool
    hits: list[Hit]
    latency_ms: float


class Profile(BaseModel):
    user_id: str
    department: str
    grade: str
    location: str
    employment_type: str
    join_date: str


# ------------------------------------------------------------------ endpoints

@app.post("/ask", response_model=AskResponse,
          summary="Answer a question as a given user",
          description=(
              "Runs generate.answer_query(question, profile, k) unchanged and "
              "returns the answer mode, the cited answer, and the ranked hits "
              "the model saw.\n\n" + AUTH_NOTE + "\n\n"
              "404 if user_id is unknown; 503 if an LLM call is needed and "
              "LLM_PROVIDER is not configured or the provider fails."))
def ask(req: AskRequest):
    profiles = load_profiles()
    profile = profiles.get(req.user_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown user_id {req.user_id!r}; known user_ids: "
                   f"{', '.join(profiles)} (see GET /profiles)")
    t0 = time.perf_counter()
    try:
        result = answer_query(req.question, profile, req.k)
    except RuntimeError as e:  # provider not configured / provider call failed
        raise HTTPException(status_code=503, detail=str(e)) from None
    latency_ms = (time.perf_counter() - t0) * 1000
    hits = [{"chunk_id": h["chunk_id"],
             "doc_id": h["metadata"]["doc_id"],
             "title": h["metadata"]["title"],
             "version": h["metadata"].get("version"),
             "effective_date": h["metadata"].get("effective_date"),
             "authority": h["authority"],
             "score": h["score"]} for h in result["hits"]]
    return {"mode": result["mode"], "answer": result["answer_text"],
            "citations": result["citations"],
            "invalid_citations": result["invalid_citations"],
            "flagged": result["flagged"], "hits": hits,
            "latency_ms": round(latency_ms, 1)}


@app.get("/profiles", response_model=list[Profile],
         summary="User profiles available to ask as")
def profiles():
    return [{f: p[f] for f in PROFILE_FIELDS} for p in load_profiles().values()]


@app.get("/health", summary="Liveness, LLM provider and chunk count")
def health():
    return {"status": "ok",
            "provider": os.environ.get("LLM_PROVIDER", "").strip().lower() or None,
            "chunks": len(retrievers._chunks())}
