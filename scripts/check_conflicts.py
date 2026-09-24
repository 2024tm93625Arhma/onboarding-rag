"""Check that standalone documents do not restate facts from versioned policies.

Every v1/v2 pair differs in one fact (manifest.csv: differing_fact, value). A
standalone document that quotes either version's value would compete with the
policy at retrieval time, so standalone documents must point to the policy
instead. This script scans each doc_kind: standalone document for those values.

A sentence is flagged when it contains a policy value (as digits or words, e.g.
"30 minutes", "thirty-minute", "INR 1,500", "two weeks" for 14 days) AND a
topic keyword for that fact, in the sentence itself or in the heading above it.
The keyword check keeps unrelated numbers such as "3 days" in a leave how-to
from being reported as the WFH allowance.

Documents with a non-empty conflicts_with are skipped: they contradict a policy
on purpose (stale restatements kept as test cases), and the conflict is
already declared in their frontmatter.

Usage: python scripts/check_conflicts.py [corpus_dir]
Exits 1 if any match is found, 0 if clean.
"""

import csv
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = ROOT / "corpus"

# differing_fact (as written in manifest.csv) -> topic keywords (regex, lower case)
TOPIC_KEYWORDS = {
    "Leave carry-forward cap": [r"carr(y|ied)", r"leave"],
    "Claim submission deadline": [r"claim", r"expense", r"receipt"],
    "Probation period length": [r"probation"],
    "Referral bonus amount": [r"referr", r"refer\b", r"bonus"],
    "Maximum WFH days per week": [r"\bwfh\b", r"from home", r"remote", r"per week", r"a week"],
    "VPN idle session timeout": [r"\bvpn\b", r"idle", r"inactiv", r"timeout", r"time out", r"session"],
    "Minimum password length": [r"password", r"passphrase"],
    "Fulfilment time for approved software requests": [r"software", r"install", r"catalogue", r"fulfil"],
    "Laptop refresh cycle": [r"laptop", r"refresh", r"replace", r"device"],
    "Asset return deadline after last working day": [r"return", r"hand(ed)? (it )?back", r"last working day",
                                                     r"equipment", r"asset"],
    "Advance desk booking window": [r"\bdesk", r"hot-?desk", r"\bseat"],
    "Monthly parking permit fee": [r"parking", r"permit"],
    "Visitor pre-registration lead time": [r"visitor", r"guest", r"pre-?regist"],
    "Minimum advance booking for domestic flights": [r"flight", r"air ?(fare|line|ticket)", r"travel"],
    "Daily meal allowance on domestic travel": [r"meal", r"allowance", r"food", r"per diem"],
}

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
        "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# unit -> regex for the unit word(s) that may follow the number
UNITS = {
    "day": r"days?",
    "month": r"months?",
    "minute": r"min(ute)?s?",
    "hour": r"h(ou)?rs?",
    "year": r"y(ea)?rs?",
    "character": r"char(acter)?s?",
}
CURRENCY = r"(?:INR|Rs\.?|₹)"


def number_words(n):
    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f"[\\s-]{ONES[ones]}" if ones else "")


def number_pattern(n):
    """Regex matching n as digits (with or without thousands separators) or words."""
    digits = f"{n:,}".replace(",", ",?")
    forms = [rf"(?<![\d,.]){digits}(?![\d,])"]
    if n < 100:
        forms.append(rf"\b{number_words(n)}\b")
    return "(?:" + "|".join(forms) + ")"


def parse_value(value):
    """Turn a manifest value such as '12 unused leave days' or 'INR 1,500' into a regex."""
    m = re.fullmatch(rf"{CURRENCY}\s*([\d,]+)", value.strip())
    if m:
        n = int(m.group(1).replace(",", ""))
        num = number_pattern(n)
        return rf"{CURRENCY}\s*{num}|{num}\s*(?:INR|rupees)"
    m = re.match(r"(\d+)[\s-]+(.*)", value.strip())
    if not m:
        return None
    n = int(m.group(1))
    last = re.split(r"[\s-]+", m.group(2))[-1].lower().rstrip("s")
    unit = UNITS.get(last)
    if unit is None:
        return None
    # allow up to two qualifier words between number and unit: "3 business days"
    pattern = rf"{number_pattern(n)}[\s-]+(?:[a-z]+[\s-]+){{0,2}}?{unit}\b"
    if last == "day" and n % 7 == 0:
        weeks = n // 7
        week_word = "a" if weeks == 1 else number_words(weeks)
        pattern += rf"|(?:{number_pattern(weeks)}|\b{week_word})[\s-]+weeks?\b"
        if weeks == 2:
            pattern += r"|\bfortnight\b"
    return pattern


def load_facts(corpus):
    """Return {differing_fact: {"values": [...], "pattern": regex, "keywords": regex or None}}."""
    with (corpus / "manifest.csv").open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["version"] and r["differing_fact"]]
    facts = {}
    for r in rows:
        fact = facts.setdefault(r["differing_fact"], {"values": [], "parts": []})
        if r["value"] in fact["values"]:
            continue
        part = parse_value(r["value"])
        if part is None:
            print(f"WARN  {r['doc_id']}: cannot parse manifest value '{r['value']}'; matching it verbatim")
            part = re.escape(r["value"])
        fact["values"].append(r["value"])
        fact["parts"].append(part)
    for name, fact in facts.items():
        fact["pattern"] = re.compile("|".join(f"(?:{p})" for p in fact["parts"]), re.I)
        keywords = TOPIC_KEYWORDS.get(name)
        if keywords is None:
            print(f"WARN  no topic keywords for '{name}'; matching its values without a topic check")
        fact["keywords"] = re.compile("|".join(keywords), re.I) if keywords else None
    return facts


def load_standalone(corpus):
    """Return ({doc_id: body} to check, [doc_ids skipped because conflicts_with is set])."""
    docs, declared = {}, []
    for path in sorted(corpus.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            continue
        meta = yaml.safe_load(m.group(1)) or {}
        if meta.get("doc_kind") != "standalone":
            continue
        doc_id = meta.get("doc_id", path.stem)
        if meta.get("conflicts_with"):
            declared.append(doc_id)
        else:
            docs[doc_id] = m.group(2)
    return docs, declared


def segments(body):
    """Yield (heading, text) for each paragraph, list item or table row."""
    heading = ""
    current = []

    def flush():
        if current:
            yield heading, " ".join(current)
            current.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            yield from flush()
        elif stripped.startswith("#"):
            yield from flush()
            heading = stripped.lstrip("#").strip()
        elif re.match(r"^([-*|]|\d+\.)\s*", stripped) and not re.match(r"^\*\*", stripped):
            yield from flush()
            current.append(stripped)
        else:
            current.append(stripped)
    yield from flush()


def sentences(text):
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*\"(])", text):
        s = re.sub(r"\s+", " ", s).strip()
        # drop list and table markup so the printed sentence reads cleanly
        s = re.sub(r"^(?:[-*]|\d+\.)\s+", "", s).strip(" |").replace(" | ", " / ")
        if s:
            yield s


def main():
    corpus = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CORPUS
    facts = load_facts(corpus)
    docs, declared = load_standalone(corpus)
    print(f"Checking {len(docs)} standalone documents against {len(facts)} versioned facts")
    print(f"Skipping {len(declared)} with a declared conflict (conflicts_with set)\n")

    hits = 0
    for doc_id, body in docs.items():
        for heading, text in segments(body):
            for sentence in sentences(text):
                for name, fact in facts.items():
                    m = fact["pattern"].search(sentence)
                    if not m:
                        continue
                    if fact["keywords"] and not fact["keywords"].search(f"{heading} {sentence}"):
                        continue
                    hits += 1
                    print(f"{doc_id}: {name} ('{m.group(0)}'; policy values: {', '.join(fact['values'])})")
                    print(f"    {sentence}\n")

    print(f"{hits} conflicting sentence(s) found" if hits else "Clean: no versioned policy values found")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
