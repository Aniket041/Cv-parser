"""Stated total first; otherwise union of employment date intervals."""
import re
from datetime import date

MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DATE = r"(?:[A-Za-z]{3,9}\.?\s*['\u2019\u2018\u02bc-]?\s*(?:\d{4}|\d{2})|\d{1,2}[/.-]\d{4}|(?:19|20)\d{2})"
RANGE = re.compile(rf"\b({DATE})\s*(?:-|\u2013|\u2014|to|till(?!\s+date)|(?=till\s+date))\s*(present|current|continue|continuing|till\s+date|{DATE})\b", re.I)
WORK = re.compile(r"(?:professional |work |employment |career )?(?:experience|history)|employment", re.I)
STOP = re.compile(r"^(?:education|academic|qualifications?|skills|certifications?|personal details|projects)\b", re.I)
JOB = re.compile(r"engineer|manager|consultant|developer|analyst|officer|executive|worked|company|ltd|inc\b|pvt", re.I)


def month_index(value: str, end: bool = False) -> int | None:
    now = date.today()
    value = value.lower().strip()
    if value in {"present", "current", "continue", "continuing", "till date"}:
        return now.year * 12 + now.month - 1
    if re.fullmatch(r"\d{4}", value):
        return int(value) * 12 + (11 if end else 0)
    match = re.fullmatch(r"(\d{1,2})[/.-](\d{4})", value)
    if match:
        month, year = int(match[1]), int(match[2])
        return year * 12 + month - 1 if 1 <= month <= 12 else None
    match = re.fullmatch(r"([a-z]+)\.?\s*['\u2019\u2018\u02bc-]?\s*(\d{4}|\d{2})", value)
    if match and match[1][:3] in MONTH_NAMES:
        year = int(match[2])
        if len(match[2]) == 2:
            year += 2000 if year <= now.year % 100 else 1900
        return year * 12 + MONTH_NAMES.index(match[1][:3])
    return None


def normalize_work_text(text: str) -> str:
    # A PDF can place the end of a date range on the next physical line.
    text = re.sub(r"(?im)(\b(?:designation|position|role|company))\s*\n\s*(:)", r"\1 \2", text)
    return re.sub(rf"({DATE})[ \t]*(to|[-\u2013\u2014])[ \t]*\n\s*(?=(?:till|present|current|[A-Za-z]{{3}}|\d))", r"\1 \2 ", text, flags=re.I)


def employment_ranges(text: str) -> list[tuple[int, int, str]]:
    active = False
    output = []
    lines = [line.strip() for line in normalize_work_text(text).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if STOP.search(line.strip()):
            active = False
        elif WORK.search(line) and len(line) < 100:
            active = True
        context = "\n".join(lines[max(0, index - 1):index + 1])
        if not active and not JOB.search(context):
            continue
        if STOP.search(line.strip()):
            continue
        for match in RANGE.finditer(line):
            start, end = month_index(match[1]), month_index(match[2], True)
            now = date.today().year * 12 + date.today().month - 1
            if start is not None and end is not None and start <= end <= now and end - start < 720:
                output.append((start, end, context))
    return output


def calculated_years(text: str) -> float | None:
    intervals = sorted(employment_ranges(text))
    merged = []
    for start, end, _ in intervals:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return round(sum(end - start + 1 for start, end in merged) / 12, 1) if merged else None


def experience_value(text: str) -> tuple[str, str]:
    duration = r"(?P<years>\d{1,2}(?:\.\d+)?)\s*(?P<plus>\+)?\s*(?:years?|yrs?)(?:\s*(?:and)?\s*(?P<months>\d{1,2})\s*(?:months?|mos?))?"
    patterns = [
        rf"(?:total|overall|work|professional)\s+(?:work\s+|professional\s+)?experience\s*\(\s*{duration}\s*\)",
        rf"(?:total|overall)\s+(?:work\s+|professional\s+)?experience\s*(?:of|:|-)?\s*{duration}",
        rf"(?:total|overall)\s+(?:of\s+)?{duration}\s*(?:of\s+)?(?:work\s+|professional\s+)?experience",
        # Real CVs pad this phrase freely: "25 years of rich & extensive experience",
        # "4+ years of extensive experience as full stack developer". Allow any short
        # run of adjectives, but no punctuation, so the match cannot cross a sentence.
        rf"(?:over|more than|about|approximately)?\s*{duration}\s+(?:of\s+)?(?:[A-Za-z&+/-]+\s+){{0,4}}experience",
        rf"(?:work\s+|professional\s+)?experience\s*(?:of|:|-)?\s*{duration}",
        rf"{duration}\s*(?:of\s+)?(?:work\s+|professional\s+)?experience",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            result = f"{match['years']}{match['plus'] or ''} years"
            if match['months']:
                result += f" {match['months']} months"
            return result, match.group()
    calculated = calculated_years(text)
    if calculated is not None:
        evidence = "\n".join(context for _, _, context in employment_ranges(text))
        return f"{calculated:g} years", "Calculated from employment dates (overlaps counted once):\n" + evidence
    return "", ""
