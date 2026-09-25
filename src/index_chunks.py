"""Embed chunks and load them into a persistent ChromaDB collection.

Step 2 of 2: reads data/chunks.jsonl (written by src/ingest.py), embeds each
chunk's chunk_text with all-MiniLM-L6-v2 and writes the vectors, the chunk_body
and the full chunk metadata to data/chroma/.

Metadata:
- Chroma metadata values must be str, int, float or bool, so the list fields
  (applies_if, conflicts_with, department_scope) are stored as JSON strings.
  Decode them with json.loads at query time.
- Scalar fields keep their native types. A field whose value is None (version
  on unversioned docs, superseded_by on docs nothing replaces) is left out of
  that chunk's metadata, because Chroma cannot store or filter on nulls.
- chunk_id, parent_doc_id, section_heading and section_index are stored too.

Idempotent: the collection is deleted and rebuilt on every run.

Usage: python src/index_chunks.py
"""

import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHUNKS_IN = DATA / "chunks.jsonl"
CHROMA_DIR = DATA / "chroma"

COLLECTION = "chunks"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
JSON_FIELDS = ("applies_if", "conflicts_with", "department_scope")
CHUNK_FIELDS = ("chunk_id", "parent_doc_id", "section_heading", "section_index")
BATCH_SIZE = 256


def load_chunks(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chroma_metadata(chunk):
    meta = {field: chunk[field] for field in CHUNK_FIELDS}
    for key, value in chunk["metadata"].items():
        if key in JSON_FIELDS:
            meta[key] = json.dumps(value)
        elif value is None:
            continue
        elif isinstance(value, (str, int, float, bool)):
            meta[key] = value
        else:
            raise TypeError(f"{chunk['chunk_id']}: unsupported metadata {key}={value!r}")
    return meta


def get_collection(client=None):
    """Open the existing collection for querying."""
    client = client or chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(COLLECTION)


def build_index(chunks, model):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine", "embedding_model": MODEL_NAME},
    )

    embeddings = model.encode(
        [c["chunk_text"] for c in chunks],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            embeddings=embeddings[start:start + BATCH_SIZE].tolist(),
            documents=[c["chunk_body"] for c in batch],
            metadatas=[chroma_metadata(c) for c in batch],
        )
    return collection


def main():
    chunks = load_chunks(CHUNKS_IN)
    ids = [c["chunk_id"] for c in chunks]
    if len(set(ids)) != len(ids):
        sys.exit("duplicate chunk_id in chunks.jsonl; re-run src/ingest.py")

    model = SentenceTransformer(MODEL_NAME)
    collection = build_index(chunks, model)
    print(f"indexed {collection.count()} chunks into {CHROMA_DIR} "
          f"(collection '{COLLECTION}', model {MODEL_NAME})")


if __name__ == "__main__":
    main()
