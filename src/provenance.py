"""Shared provenance logic: user profiles, applicability, access scope, policy families.

- load_profiles: user_id -> profile dict, from data/user_profiles.json.
- applies_to:    does a chunk's applies_if hold for a profile? Every condition
                 must hold (AND); an empty list applies to everyone. Values that
                 are ISO dates on both sides are compared as dates, everything
                 else as plain strings.
- in_scope:      may the profile see the chunk at all? The chunk's
                 department_scope must contain the profile's department or
                 "all", and the profile's grade must be at least min_grade when
                 the chunk sets one. Grades run G1 (lowest) to G7.
- policy_family: doc_id with the "-vN" suffix removed, so hr-leave-policy-v1 and
                 hr-leave-policy-v2 both map to hr-leave-policy.

applies_to decides which version of a policy is right for the user; in_scope
decides whether the user may see the document. A chunk can be in scope and
still not apply (a pre-2025 leave rule shown to a 2026 joiner).
"""

import json
import operator
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_IN = ROOT / "data" / "user_profiles.json"

VERSION_SUFFIX = re.compile(r"-v\d+$")
GRADES = [f"G{i}" for i in range(1, 8)]
GRADE_RANK = {g: i for i, g in enumerate(GRADES)}

OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


@lru_cache(maxsize=1)
def load_profiles():
    with PROFILES_IN.open(encoding="utf-8") as f:
        return {p["user_id"]: p for p in json.load(f)}


def _as_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _coerce(left, right):
    """Compare as dates when both sides parse as ISO dates, else as strings."""
    dl, dr = _as_date(left), _as_date(right)
    if dl is not None and dr is not None:
        return dl, dr
    return str(left), str(right)


def _holds(condition, profile):
    value = profile.get(condition["field"])
    if value is None:
        return False  # a condition on an unknown field cannot be shown to hold
    op = condition["op"]
    if op not in OPS:
        raise ValueError(f"unknown applies_if op: {op!r}")
    left, right = _coerce(value, condition["value"])
    return OPS[op](left, right)


def applies_to(chunk, profile):
    return all(_holds(c, profile) for c in chunk["metadata"].get("applies_if") or [])


def in_scope(chunk, profile):
    meta = chunk["metadata"]
    scope = meta.get("department_scope") or []
    if "all" not in scope and profile["department"] not in scope:
        return False
    min_grade = meta.get("min_grade")
    if min_grade is not None and GRADE_RANK[profile["grade"]] < GRADE_RANK[min_grade]:
        return False
    return True


def policy_family(chunk):
    return VERSION_SUFFIX.sub("", chunk["metadata"]["doc_id"])
