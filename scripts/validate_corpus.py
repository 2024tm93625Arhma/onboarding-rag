"""Validate the policy corpus in corpus/ against its frontmatter rules and manifest.csv.

Usage: python scripts/validate_corpus.py
Exits 1 if any check fails.
"""

import csv
import datetime as dt
import difflib
import re
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
MANIFEST = CORPUS / "manifest.csv"

MAX_V2_EFFECTIVE = dt.date(2026, 9, 1)
MAX_PAIR_DIFF_LINES = 3

# field -> allowed types
REQUIRED = {
    "doc_id": str,
    "title": str,
    "doc_kind": str,
    "version": (int, type(None)),
    "effective_date": dt.date,
    "status": str,
    "superseded_by": (str, type(None)),
    "applies_if": list,
    "conflicts_with": list,
    "sensitivity": str,
    "department_scope": list,
    "owner": str,
}
STATUSES = {"current", "superseded"}
POLICY_VERSION = "policy_version"  # one half of a v1/v2 pair
STANDALONE = "standalone"  # not versioned; never superseded
DOC_KINDS = {POLICY_VERSION, STANDALONE}
VERSION_SUFFIX = re.compile(r"-v\d+$")
COND_FIELDS = {"join_date", "department", "employment_type", "location"}
COND_OPS = {"==", "!=", "<", "<=", ">", ">="}

# Lines that are allowed to exist only in v2: they announce the replacement of v1.
REPLACES_V1 = re.compile(r"replaces v1|remain under v1", re.I)
VERSION_TAG = re.compile(r"\(v\d+\)")


class Report:
    def __init__(self):
        self.failures = 0

    def section(self, title):
        print(f"\n== {title} " + "=" * max(0, 60 - len(title)))

    def fail(self, msg):
        self.failures += 1
        print(f"  FAIL  {msg}")

    def ok(self, msg):
        print(f"  ok    {msg}")


def load_docs(report):
    docs = {}
    for path in sorted(CORPUS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            report.fail(f"{path.name}: no frontmatter block")
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            report.fail(f"{path.name}: invalid YAML: {e}")
            continue
        docs[path.stem] = {"path": path, "meta": meta, "body": m.group(2)}
    return docs


def check_frontmatter(docs, report):
    report.section("Frontmatter fields and types")
    before = report.failures
    for stem, d in docs.items():
        meta = d["meta"]
        for field, types in REQUIRED.items():
            if field not in meta:
                report.fail(f"{stem}: missing field '{field}'")
            elif not isinstance(meta[field], types) or isinstance(meta[field], bool):
                report.fail(f"{stem}: '{field}' has type {type(meta[field]).__name__}")
        if meta.get("doc_id") != stem:
            report.fail(f"{stem}: doc_id '{meta.get('doc_id')}' does not match filename")
        if meta.get("status") not in STATUSES:
            report.fail(f"{stem}: status '{meta.get('status')}' not in {sorted(STATUSES)}")
        if meta.get("status") == "superseded" and not meta.get("superseded_by"):
            report.fail(f"{stem}: status superseded but superseded_by is empty")
        if meta.get("status") == "current" and meta.get("superseded_by"):
            report.fail(f"{stem}: status current but superseded_by is set")
        kind = meta.get("doc_kind")
        if kind not in DOC_KINDS:
            report.fail(f"{stem}: doc_kind '{kind}' not in {sorted(DOC_KINDS)}")
        elif kind == POLICY_VERSION:
            if meta.get("version") is None:
                report.fail(f"{stem}: policy_version document has version null")
            elif not stem.endswith(f"-v{meta.get('version')}"):
                report.fail(f"{stem}: version {meta.get('version')} does not match doc_id suffix")
        else:  # standalone
            if meta.get("version") is not None:
                report.fail(f"{stem}: standalone document must have version null")
            if meta.get("status") != "current":
                report.fail(f"{stem}: standalone document must have status current")
            if meta.get("superseded_by") is not None:
                report.fail(f"{stem}: standalone document must have superseded_by null")
            if VERSION_SUFFIX.search(stem):
                report.fail(f"{stem}: standalone doc_id must not have a -vN suffix")
        for i, c in enumerate(meta.get("applies_if") or []):
            where = f"{stem}: applies_if[{i}]"
            if not isinstance(c, dict) or set(c) != {"field", "op", "value"}:
                report.fail(f"{where} must be {{field, op, value}}, got {c!r}")
                continue
            if c["field"] not in COND_FIELDS:
                report.fail(f"{where}: unknown field '{c['field']}'")
            if c["op"] not in COND_OPS:
                report.fail(f"{where}: unknown op '{c['op']}'")
            if c["field"] == "join_date" and not isinstance(c["value"], dt.date):
                report.fail(f"{where}: join_date value is not a date")
    if report.failures == before:
        report.ok(f"{len(docs)} documents")


def check_pairs(docs, report):
    """Returns [(v1_stem, v2_stem)] for pairs that are structurally valid.

    Only doc_kind: policy_version documents take part in pairing.
    """
    report.section("Supersession links and pairing (policy_version only)")
    before = report.failures
    versioned = {s: d for s, d in docs.items() if d["meta"].get("doc_kind") == POLICY_VERSION}
    pairs = []
    pointed_to = {}
    for stem, d in versioned.items():
        target = d["meta"].get("superseded_by")
        if not target:
            continue
        if target not in docs:
            report.fail(f"{stem}: superseded_by '{target}' does not exist")
            continue
        if target not in versioned:
            report.fail(f"{stem}: superseded_by '{target}' is not a policy_version document")
            continue
        pointed_to.setdefault(target, []).append(stem)

    for stem, d in versioned.items():
        version = d["meta"].get("version")
        if version == 1 and not d["meta"].get("superseded_by"):
            report.fail(f"{stem}: v1 with no v2 (orphan)")
        if version == 2:
            sources = pointed_to.get(stem, [])
            if len(sources) != 1:
                report.fail(f"{stem}: superseded by {len(sources)} v1 docs {sources}, expected 1")
                continue
            v1 = sources[0]
            if docs[v1]["meta"].get("version") != 1:
                report.fail(f"{v1}: points to {stem} but is not version 1")
                continue
            if v1.removesuffix("-v1") != stem.removesuffix("-v2"):
                report.fail(f"{v1} -> {stem}: base doc names differ")
            pairs.append((v1, stem))
        if version not in (1, 2):
            report.fail(f"{stem}: version {version} (only 1 and 2 are expected)")
    if report.failures == before:
        standalone = len(docs) - len(versioned)
        report.ok(f"{len(pairs)} pairs, no orphans ({standalone} standalone documents skipped)")
    return pairs


def comparable_lines(body, is_v2):
    lines = [VERSION_TAG.sub("(vN)", line.rstrip()) for line in body.strip().splitlines()]
    if is_v2:
        lines = [line for line in lines if not REPLACES_V1.search(line)]
    return lines


def check_pair_bodies(docs, pairs, report):
    report.section(f"Pair body diffs (flag > {MAX_PAIR_DIFF_LINES} lines)")
    print(f"  (ignores the (v1)/(v2) heading tag and v2 lines matching /{REPLACES_V1.pattern}/)")
    for v1, v2 in pairs:
        a = comparable_lines(docs[v1]["body"], is_v2=False)
        b = comparable_lines(docs[v2]["body"], is_v2=True)
        ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
        changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
        base = v1.removesuffix("-v1")
        if changed > MAX_PAIR_DIFF_LINES:
            report.fail(f"{base:28} {changed} differing lines")
            for line in difflib.unified_diff(a, b, lineterm="", n=0):
                if line.startswith(("-", "+")) and not line.startswith(("---", "+++")):
                    print(f"          {line}")
        else:
            report.ok(f"{base:28} {changed} differing lines")


def check_effective_dates(docs, report):
    report.section(f"v2 effective_date <= {MAX_V2_EFFECTIVE}")
    before = report.failures
    for stem, d in docs.items():
        eff = d["meta"].get("effective_date")
        if d["meta"].get("version") == 2 and isinstance(eff, dt.date) and eff > MAX_V2_EFFECTIVE:
            report.fail(f"{stem}: effective_date {eff}")
    if report.failures == before:
        report.ok("all v2 effective dates in range")


def check_manifest(docs, report):
    report.section("manifest.csv")
    before = report.failures
    if not MANIFEST.exists():
        report.fail("corpus/manifest.csv not found")
        return
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    listed = {r["doc_id"] for r in rows}
    for missing in sorted(set(docs) - listed):
        report.fail(f"{missing}: in corpus/ but not in manifest")
    for extra in sorted(listed - set(docs)):
        report.fail(f"{extra}: in manifest but no document")
    for r in rows:
        d = docs.get(r["doc_id"])
        if d is None:
            continue
        # contract: value must be an exact substring of the body
        if r["value"] not in d["body"]:
            report.fail(f"{r['doc_id']}: manifest value '{r['value']}' is not a verbatim substring of body")
            continue
        # word-boundary match so "5 days" does not match inside "15 days"
        pattern = r"(?<![\w.,])" + re.escape(r["value"]) + r"(?![\w])"
        if not re.search(pattern, d["body"]):
            report.fail(f"{r['doc_id']}: manifest value '{r['value']}' only occurs inside a larger token")
    if report.failures == before:
        report.ok(f"{len(rows)} rows, every value found verbatim in its document")


def report_word_counts(docs):
    print("\n== Word counts (body only) " + "=" * 34)
    counts = {stem: len(d["body"].split()) for stem, d in docs.items()}
    for stem, n in sorted(counts.items(), key=lambda kv: kv[1]):
        print(f"  {n:5}  {stem}")
    values = list(counts.values())
    print(f"  min {min(values)}  max {max(values)}  median {statistics.median(values):g}")


def main():
    report = Report()
    docs = load_docs(report)
    if not docs:
        print("No documents found in corpus/")
        return 1
    check_frontmatter(docs, report)
    pairs = check_pairs(docs, report)
    check_pair_bodies(docs, pairs, report)
    check_effective_dates(docs, report)
    check_manifest(docs, report)
    report_word_counts(docs)
    print(f"\n{report.failures} problem(s) found" if report.failures else "\nAll checks passed")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
