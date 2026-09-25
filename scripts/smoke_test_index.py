"""Smoke test for the Chroma index: one unfiltered query and one status filter.

Usage: python scripts/smoke_test_index.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sentence_transformers import SentenceTransformer

from index_chunks import MODEL_NAME, get_collection

QUERY = "how many leave days can I carry forward"
TOP_K = 5


def show(title, result):
    print(f"\n=== {title} ===")
    rows = zip(result["ids"][0], result["metadatas"][0],
               result["documents"][0], result["distances"][0])
    for rank, (chunk_id, meta, body, dist) in enumerate(rows, 1):
        first_line = next((l for l in body.splitlines() if l.strip()), "")
        print(f"{rank}. {chunk_id}  (cosine dist {dist:.3f})")
        print(f"   doc_id={meta['doc_id']}  version={meta.get('version')}  "
              f"status={meta['status']}  applies_if={json.loads(meta['applies_if'])}")
        print(f"   {first_line[:110]}")


def main():
    collection = get_collection()
    model = SentenceTransformer(MODEL_NAME)
    q = model.encode([QUERY], normalize_embeddings=True).tolist()
    print(f"collection size: {collection.count()}  query: {QUERY!r}")

    show("unfiltered", collection.query(query_embeddings=q, n_results=TOP_K))

    filtered = collection.query(query_embeddings=q, n_results=TOP_K,
                                where={"status": "current"})
    show("where status = current", filtered)
    statuses = {m["status"] for m in filtered["metadatas"][0]}
    assert statuses == {"current"}, f"filter leaked: {statuses}"
    print("\nfilter check passed: all filtered results have status=current")


if __name__ == "__main__":
    main()
