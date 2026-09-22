"""Confidence derived from evidence quality, not from how many fields are filled.

The previous score counted populated fields, so a record where every value was
confidently wrong scored the same as one where every value was right. Nothing
about "a value exists" says the value is correct.

What can actually be known without ground truth:

  - how the value was obtained (an explicitly labelled "Company :" line is worth
    more than a value recovered by splitting a header on punctuation)
  - whether two independent extractors agree (the deterministic rules and the
    local model are computed separately for designation and company; agreement
    between them is the single strongest signal available, and it is free)
  - whether the value is structurally plausible (a phone with 10-13 digits, a
    qualification carrying its own passing year)
  - whether the text itself is trustworthy (OCR output is not)

A field that is legitimately absent scores 0 and drags the record to review,
which is the intended behaviour: a record missing its employer is not ready to
export regardless of how good its email is.
"""
from __future__ import annotations

import re

# Fields that must be sound before a record can skip human review. Locations and
# phone are excluded: they are noisy by nature and rarely the reason an export
# is wrong in a way that matters.
CRITICAL = ("name", "email", "total_experience_years", "latest_designation",
            "latest_company", "qualifications")

WEIGHTS = {
    "name": 1.0, "email": 0.8, "phone": 0.6, "total_experience_years": 1.0,
    "latest_designation": 1.2, "latest_company": 1.2, "locations": 0.4,
    "qualifications": 1.0,
}

READY_OVERALL = 0.75
READY_FLOOR = 0.5


def values_agree(first: str, second: str) -> bool:
    """Do two extractors name the same thing, allowing for punctuation and suffixes?"""
    def key(value: str) -> set[str]:
        plain = re.sub(r"[^\w\s]", " ", (value or "").lower())
        plain = re.sub(r"\b(?:pvt|private|ltd|limited|llp|inc|corp|corporation|co|company)\b", " ", plain)
        return {token for token in plain.split() if len(token) > 1}

    left, right = key(first), key(second)
    if not left or not right:
        return False
    return len(left & right) / min(len(left), len(right)) >= 0.6


def _phone_score(value: str) -> float:
    if not value:
        return 0.0
    digits = len(re.sub(r"\D", "", value))
    return 0.85 if 10 <= digits <= 13 else 0.5


def field_scores(signals: dict) -> dict[str, float]:
    """Score each field 0..1 from how its value was obtained."""
    name = signals.get("name", "")
    scores = {
        "name": 0.0 if not name else (0.95 if signals.get("name_from_filename") else 0.65),
        "email": 0.95 if signals.get("email") else 0.0,
        "phone": _phone_score(signals.get("phone", "")),
        "locations": 0.65 if signals.get("locations") else 0.0,
    }

    experience = signals.get("total_experience_years", "")
    # A stated total is authoritative; a figure merged from date ranges inherits
    # every parsing error in those ranges.
    scores["total_experience_years"] = 0.0 if not experience else (
        0.9 if signals.get("experience_stated") else 0.55)

    qualification = signals.get("qualifications", "")
    scores["qualifications"] = 0.0 if not qualification else (
        0.8 if signals.get("qualification_year") else 0.55)

    # Agreement between the rules and the local model, computed independently.
    agreement = signals.get("employment_agreement", {})
    for field in ("latest_designation", "latest_company"):
        value = signals.get(field, "")
        if not value:
            scores[field] = 0.0
        elif agreement.get(field) == "agree":
            scores[field] = 0.95
        elif agreement.get(field) == "conflict":
            scores[field] = 0.3
        else:
            scores[field] = 0.6  # only one extractor produced a value
    return scores


def overall(scores: dict[str, float], *, used_ocr: bool = False, is_resume: bool = True) -> float:
    total = sum(WEIGHTS.values())
    value = sum(scores.get(field, 0.0) * weight for field, weight in WEIGHTS.items()) / total
    if used_ocr:
        value *= 0.85  # OCR text is plausible-looking and frequently wrong
    if not is_resume:
        value *= 0.6
    return round(min(0.96, value), 2)


def is_ready(scores: dict[str, float], value: float, blocking: bool) -> bool:
    """Export without review only when nothing critical is weak or missing."""
    if blocking or value < READY_OVERALL:
        return False
    return all(scores.get(field, 0.0) >= READY_FLOOR for field in CRITICAL)
