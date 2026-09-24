"""Smoke test: confirm BM25 (keyword search) and sentence-transformers (semantic search) work."""

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, util

documents = [
    "New employees must complete security training in their first week.",
    "The office cafeteria serves lunch from 12pm to 2pm.",
    "To request a laptop, open a ticket with the IT helpdesk.",
    "Health insurance enrollment closes 30 days after your start date.",
]
query = "how do I get a computer"

# --- BM25: scores documents by overlapping words with the query ---
tokenized_docs = [doc.lower().split() for doc in documents]
bm25 = BM25Okapi(tokenized_docs)
bm25_scores = bm25.get_scores(query.lower().split())

print("BM25 scores (keyword match):")
for doc, score in zip(documents, bm25_scores):
    print(f"  {score:.3f}  {doc}")

# --- Sentence-transformers: scores documents by meaning, not exact words ---
model = SentenceTransformer("all-MiniLM-L6-v2")  # small model, downloaded once (~90 MB)
doc_embeddings = model.encode(documents)
query_embedding = model.encode(query)
semantic_scores = util.cos_sim(query_embedding, doc_embeddings)[0]

print("\nSemantic similarity scores (meaning match):")
for doc, score in zip(documents, semantic_scores):
    print(f"  {float(score):.3f}  {doc}")

best = documents[int(semantic_scores.argmax())]
print(f"\nBest semantic match: {best}")
print("\nBoth BM25 and sentence-transformers are working.")
