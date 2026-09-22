"""Field-level comparison rules for CV parser evaluation.

Every field is scored two ways:
  strict  - normalised exact match
  lenient - field-appropriate tolerance (abbreviations, legal suffixes, +/- 0.5 years)

Lenient is the headline number: "Sr. VP Project" vs "Sr VP Project" is not a
parser failure worth chasing, but "Page of" vs a candidate name is.
"""
from __future__ import annotations

import re

FIELDS = [
    "name", "email", "phone", "total_experience_years",
    "latest_designation", "latest_company", "locations",
    "qualifications", "qualification_years",
]

# Set-valued fields are scored by F1 over their members, not exact string match.
SET_FIELDS = {"locations"}

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")
_COMPANY_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|incorporated|corp|corporation|co|company|"
    r"technologies|technology|solutions|services|systems|india)\b", re.I)

# Ordered most-specific first: the first pattern found in the string wins.
# Each is matched against the spaced form AND the despaced form, so "B.Com",
# "b com" and "bachelorofcommerce" all reduce to the same key.
_DEGREE_CANON = [
    ("phd", r"\bph\s*d\b|\bdoctorate\b"),
    # "Master of Bussiness Adminstration" is a common misspelling in real CVs, and
    # extraction sometimes captures only the first half. Degree level is what is
    # being compared here, so "Master of Bus..." counts as an MBA either way.
    ("mba", r"\bmba\b|\bmaster\s*of\s*bus|\bmasterofbus|\bpgdm\b"),
    ("me", r"\bm\s*tech\b|\bm\s*e\b|\bmasterofengineering\b|\bmasteroftechnology\b"),
    ("be", r"\bb\s*tech\b|\bb\s*e\b|\bbachelorofengineering\b|\bbacheloroftechnology\b"),
    ("mca", r"\bmca\b"),
    ("bca", r"\bbca\b"),
    ("msc", r"\bm\s*sc\b|\bmasterofscience\b"),
    ("bsc", r"\bb\s*sc\b|\bbachelorofscience\b"),
    ("mcom", r"\bm\s*com\b|\bmasterofcommerce\b"),
    ("bcom", r"\bb\s*com\b|\bbachelorofcommerce\b"),
    ("bba", r"\bbba\b"),
    ("pgdiploma", r"\bpost\s*graduate\s*diploma\b|\bpg\s*diploma\b"),
    ("diploma", r"\bdiploma\b"),
    ("master", r"\bmaster"),
    ("bachelor", r"\bbachelor|\bgraduation\b"),
]


def _norm(value: str) -> str:
    """Casefold, drop punctuation, collapse whitespace."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", (value or "").lower())).strip()


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _years(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", value or "")
    return float(match.group(1)) if match else None


def _company_key(value: str) -> str:
    return _SPACE.sub(" ", _COMPANY_SUFFIX.sub(" ", _norm(value))).strip()


def _degree_key(value: str) -> str:
    """Reduce a qualification to its degree level.

    "Diploma in Civil Engineering" and "Diploma" are the same qualification for
    scoring purposes; the stream is not part of this field's job. B.E. and
    B.Tech are treated as one level, as they are in Indian hiring.
    """
    spaced = _norm(value)
    despaced = spaced.replace(" ", "")
    for canonical, pattern in _DEGREE_CANON:
        if re.search(pattern, spaced) or re.search(pattern, despaced):
            return canonical
    return spaced


def _members(value: str) -> set[str]:
    return {_norm(part) for part in (value or "").split(";") if _norm(part)}


def compare(field: str, expected: str, actual: str) -> tuple[bool, bool, float]:
    """Return (strict, lenient, partial_credit 0..1) for one field."""
    expected, actual = (expected or "").strip(), (actual or "").strip()

    if field in SET_FIELDS:
        want, got = _members(expected), _members(actual)
        if not want and not got:
            return True, True, 1.0
        if not want or not got:
            return False, False, 0.0
        overlap = len(want & got)
        precision = overlap / len(got)
        recall = overlap / len(want)
        f1 = 0.0 if not overlap else 2 * precision * recall / (precision + recall)
        return want == got, f1 >= 0.5, f1

    # Both blank counts as agreement: the parser correctly found nothing.
    if not expected and not actual:
        return True, True, 1.0
    if not expected or not actual:
        return False, False, 0.0

    strict = _norm(expected) == _norm(actual)

    if field == "email":
        lenient = expected.lower() == actual.lower()
    elif field == "phone":
        want, got = _digits(expected), _digits(actual)
        lenient = bool(want) and bool(got) and want[-10:] == got[-10:]
    elif field == "total_experience_years":
        want, got = _years(expected), _years(actual)
        lenient = want is not None and got is not None and abs(want - got) <= 0.5
    elif field == "latest_company":
        lenient = _company_key(expected) == _company_key(actual)
    elif field == "qualifications":
        lenient = _degree_key(expected) == _degree_key(actual)
    elif field in {"name", "latest_designation"}:
        want, got = set(_norm(expected).split()), set(_norm(actual).split())
        lenient = bool(want & got) and len(want & got) / max(len(want), len(got)) >= 0.6
    else:
        lenient = strict

    return strict, strict or lenient, 1.0 if (strict or lenient) else 0.0
