"""Load the corpus, chunk each document by section, and build the supersession graph.

Step 1 of 2: writes chunks to data/chunks.jsonl and the supersession lookup to
data/supersession.json. No embedding or vector store yet.

Chunking:
- A section starts at every `##` or `###` heading (headings inside code fences
  are ignored). A `###` section's heading is recorded as "<h2> > <h3>" so the
  subsection keeps its parent context.
- Text between the `#` title and the first section heading becomes an
  "Introduction" section. The `#` title line itself is dropped, because the
  title is already in the chunk_text prefix.
- A section whose chunk_text would reach MAX_WORDS is split on paragraph
  boundaries (blank lines outside code fences). A single paragraph that is
  still too long is split on line boundaries as a last resort.

Usage: python src/ingest.py [--seed N]
"""

import argparse
import datetime as dt
import json
import random
import re
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
CHUNKS_OUT = DATA / "chunks.jsonl"
SUPERSESSION_OUT = DATA / "supersession.json"

MAX_WORDS = 400  # every chunk_text stays strictly below this
INTRO_HEADING = "Introduction"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
HEADING = re.compile(r"^(#{1,3}) +(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def word_count(text):
    return len(text.split())


def to_json_safe(value):
    """Convert YAML dates (in frontmatter and applies_if values) to ISO strings."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    return value


def load_docs():
    docs = []
    for path in sorted(CORPUS.glob("*.md")):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        m = FRONTMATTER.match(text)
        if not m:
            sys.exit(f"{path.name}: no frontmatter block")
        meta = yaml.safe_load(m.group(1)) or {}
        if meta.get("doc_id") != path.stem:
            sys.exit(f"{path.name}: doc_id {meta.get('doc_id')!r} does not match filename")
        docs.append({"meta": to_json_safe(meta), "body": m.group(2)})
    return docs


def split_sections(body):
    """Return [(heading, text)] for the body, splitting at ## and ### outside code fences."""
    sections = []
    heading, lines = INTRO_HEADING, []
    h2 = None
    in_fence = False

    def flush():
        text = "\n".join(lines).strip()
        if text:
            sections.append((heading, text))

    for line in body.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m is None:
            lines.append(line)
            continue
        level, title = len(m.group(1)), m.group(2)
        if level == 1:
            continue  # document title; carried by the chunk_text prefix
        flush()
        lines = []
        if level == 2:
            h2 = title
            heading = title
        else:
            heading = f"{h2} > {title}" if h2 else title
    flush()
    return sections


def split_paragraphs(text):
    """Split on blank lines, but never inside a code fence."""
    paragraphs, current = [], []
    in_fence = False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if current:
                paragraphs.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def pack(units, budget, joiner):
    """Greedily pack text units into groups whose word count stays below budget."""
    groups, current, size = [], [], 0
    for unit in units:
        n = word_count(unit)
        if current and size + n >= budget:
            groups.append(joiner.join(current))
            current, size = [], 0
        current.append(unit)
        size += n
    if current:
        groups.append(joiner.join(current))
    return groups


def split_section(text, budget):
    """Split a section's text into pieces that each have fewer than `budget` words."""
    if word_count(text) < budget:
        return [text]
    units = []
    for para in split_paragraphs(text):
        if word_count(para) < budget:
            units.append(para)
        else:
            # Oversized single paragraph: fall back to line boundaries.
            units.extend(pack(para.split("\n"), budget, "\n"))
    return pack(units, budget, "\n\n")


def chunk_prefix(meta, heading):
    version = meta.get("version")
    title = meta["title"] if version is None else f"{meta['title']} (v{version})"
    return f"{title} - {heading}"


def chunk_doc(doc):
    meta = doc["meta"]
    chunks = []
    for section_index, (heading, text) in enumerate(split_sections(doc["body"])):
        prefix = chunk_prefix(meta, heading)
        budget = MAX_WORDS - word_count(prefix)
        parts = split_section(text, budget)
        for part_index, part in enumerate(parts):
            chunk_text = f"{prefix}\n\n{part}"
            if word_count(chunk_text) >= MAX_WORDS:
                sys.exit(f"{meta['doc_id']}: could not split '{heading}' below {MAX_WORDS} words")
            chunks.append({
                "chunk_id": f"{meta['doc_id']}::s{section_index:02d}p{part_index}",
                "parent_doc_id": meta["doc_id"],
                "section_index": section_index,
                "part_index": part_index,
                "part_count": len(parts),
                "section_heading": heading,
                "chunk_body": part,
                "chunk_text": chunk_text,
                "word_count": word_count(chunk_text),
                "metadata": meta,
            })
    return chunks


def build_supersession(docs):
    """Lookup in both directions: old -> new (superseded_by) and new -> [old] (supersedes)."""
    ids = {d["meta"]["doc_id"] for d in docs}
    superseded_by, supersedes = {}, {}
    for d in docs:
        old, new = d["meta"]["doc_id"], d["meta"].get("superseded_by")
        if not new:
            continue
        if new not in ids:
            sys.exit(f"{old}: superseded_by target {new!r} does not exist")
        superseded_by[old] = new
        supersedes.setdefault(new, []).append(old)
    return {
        "superseded_by": dict(sorted(superseded_by.items())),
        "supersedes": {k: sorted(v) for k, v in sorted(supersedes.items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42, help="seed for the random chunk sample")
    args = parser.parse_args()

    docs = load_docs()
    chunks = [c for d in docs for c in chunk_doc(d)]
    graph = build_supersession(docs)

    DATA.mkdir(exist_ok=True)
    with CHUNKS_OUT.open("w", encoding="utf-8", newline="\n") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    SUPERSESSION_OUT.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    per_doc = {}
    for c in chunks:
        per_doc[c["parent_doc_id"]] = per_doc.get(c["parent_doc_id"], 0) + 1
    counts = list(per_doc.values())
    words = [c["word_count"] for c in chunks]
    split_sections_n = sum(1 for c in chunks if c["part_index"] == 1)

    print(f"Documents:        {len(docs)}")
    print(f"Total chunks:     {len(chunks)}")
    print(f"Chunks per doc:   min {min(counts)}, max {max(counts)}, median {statistics.median(counts)}")
    print(f"Words per chunk:  min {min(words)}, max {max(words)}, median {statistics.median(words)}")
    print(f"Sections split on paragraphs: {split_sections_n}")
    print(f"Supersession edges: {len(graph['superseded_by'])}")
    print(f"Wrote {CHUNKS_OUT.relative_to(ROOT)} and {SUPERSESSION_OUT.relative_to(ROOT)}")

    print(f"\n== 5 random chunks (seed {args.seed}) " + "=" * 30)
    for c in random.Random(args.seed).sample(chunks, 5):
        print(f"\n--- {c['chunk_id']}  ({c['word_count']} words, part {c['part_index'] + 1}/{c['part_count']})")
        print(json.dumps(c["metadata"], ensure_ascii=False))
        print(c["chunk_text"])


if __name__ == "__main__":
    main()
