"""Check data/chunks.jsonl against manifest.csv and the corpus frontmatter.

For every manifest row with a value:
1. Exactly one chunk of that row's document contains the value verbatim in its
   chunk_body, using the same whole-token match as validate_corpus.py (so
   "5 days" does not match inside "15 days"). Zero hits means the value was
   lost or cut across a chunk boundary; more than one means it is duplicated.
2. That chunk's metadata equals the document's frontmatter, freshly parsed
   from corpus/ (dates compared as ISO strings).
3. The row's gold_chunk_id is that chunk's chunk_id, so gold labels cannot
   drift silently when the chunking changes.

With --write-gold, check 3 is replaced by filling in gold_chunk_id (the chunk
holding the value; empty for rows without one) and rewriting manifest.csv.
The manifest is written only if checks 1 and 2 pass for every row.

Occurrences of a value in other documents' chunks are listed for information
only; conflicting documents repeat v1 values on purpose.

Run src/ingest.py first.
Usage: python scripts/check_chunks.py [--write-gold]
Exits 1 if any check fails.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
MANIFEST = CORPUS / "manifest.csv"
CHUNKS = ROOT / "data" / "chunks.jsonl"


def load_frontmatter():
    """doc_id -> frontmatter, normalised the way JSON stores it (dates -> ISO strings)."""
    meta = {}
    for path in sorted(CORPUS.glob("*.md")):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            sys.exit(f"{path.name}: no frontmatter block")
        fm = yaml.safe_load(m.group(1)) or {}
        meta[path.stem] = json.loads(json.dumps(fm, default=str))
    return meta


def value_pattern(value):
    # same boundary rule as validate_corpus.py
    return re.compile(r"(?<![\w.,])" + re.escape(value) + r"(?![\w])")


def write_manifest(fieldnames, rows):
    if "gold_chunk_id" not in fieldnames:
        fieldnames = fieldnames + ["gold_chunk_id"]
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-gold", action="store_true",
                        help="fill in gold_chunk_id in manifest.csv instead of checking it")
    args = parser.parse_args()

    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS.relative_to(ROOT)} not found; run src/ingest.py first")
    chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
    frontmatter = load_frontmatter()
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
        fieldnames = reader.fieldnames
    rows = [r for r in all_rows if r["value"].strip()]
    gold = {}  # doc_id -> chunk_id holding that row's value

    failures = 0
    elsewhere = []

    def fail(msg):
        nonlocal failures
        failures += 1
        print(f"  FAIL  {msg}")

    print(f"== Manifest values vs chunks ({len(rows)} rows with a value) " + "=" * 10)
    for r in rows:
        doc_id, value = r["doc_id"], r["value"]
        pattern = value_pattern(value)
        hits = [c for c in chunks if pattern.search(c["chunk_body"])]
        own = [c for c in hits if c["parent_doc_id"] == doc_id]
        others = sorted({c["parent_doc_id"] for c in hits} - {doc_id})
        if others:
            elsewhere.append((doc_id, value, others))

        if len(own) != 1:
            ids = ", ".join(c["chunk_id"] for c in own) or "none"
            fail(f"{doc_id}: '{value}' found in {len(own)} of its chunks (expected 1): {ids}")
            continue

        chunk = own[0]
        expected = frontmatter.get(doc_id)
        if expected is None:
            fail(f"{doc_id}: in manifest but no document in corpus/")
            continue
        actual = chunk["metadata"]
        if actual != expected:
            diffs = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
            for k in diffs:
                fail(f"{chunk['chunk_id']}: metadata {k} = {actual.get(k)!r}, frontmatter has {expected.get(k)!r}")
            continue
        gold[doc_id] = chunk["chunk_id"]
        if not args.write_gold and r.get("gold_chunk_id") != chunk["chunk_id"]:
            fail(f"{doc_id}: gold_chunk_id is {r.get('gold_chunk_id')!r}, but '{value}' is in {chunk['chunk_id']}")
            continue
        print(f"  ok    {chunk['chunk_id']:<45} '{value}'")

    print(f"\n== Values also found in other documents (info) " + "=" * 13)
    for doc_id, value, others in elsewhere:
        print(f"  {doc_id}: '{value}' also in {', '.join(others)}")
    if not elsewhere:
        print("  none")

    if args.write_gold:
        if failures:
            print("\nmanifest.csv not written: fix the failures above first")
        else:
            for r in all_rows:
                r["gold_chunk_id"] = gold.get(r["doc_id"], "")
            write_manifest(fieldnames, all_rows)
            print(f"\nWrote gold_chunk_id for {len(gold)} rows to {MANIFEST.relative_to(ROOT)}")

    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
