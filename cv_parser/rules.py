"""Deterministic, explainable extraction rules used before the local LLM."""
from __future__ import annotations

import re


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
LOCATION_WORDS = {
    "ahmedabad", "bangalore", "bengaluru", "bhopal", "bhubaneswar", "chandigarh", "chennai", "coimbatore", "delhi",
    "faridabad", "gurgaon", "gurugram", "hyderabad", "indore", "jaipur", "kolkata", "mumbai", "nagpur", "nashik",
    "noida", "pune", "surat", "thane", "vadodara", "visakhapatnam", "dubai", "abu dhabi", "doha", "riyadh", "singapore",
}


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def snippet(text: str, needle: str, width: int = 180) -> str:
    index = text.lower().find(needle.lower()) if needle else -1
    if index < 0:
        return normalized(text)[:width]
    return normalized(text[max(0, index - width // 3): index + len(needle) + width])[:width]


def find_email(text: str) -> tuple[str, str]:
    match = EMAIL_PATTERN.search(text)
    return (match.group(0), snippet(text, match.group(0))) if match else ("", "")


# "2012-2016" has eight digits and used to be accepted as a phone number.
YEAR_RANGE = re.compile(r"^\s*(?:19|20)\d{2}\s*[-–—/]\s*(?:19|20)\d{2}\s*$")


def find_phone(text: str) -> tuple[str, str]:
    for match in PHONE_PATTERN.finditer(text):
        value = match.group(0).strip()
        digits = re.sub(r"\D", "", value)
        # A subscriber number is at least 10 digits everywhere this parser is used;
        # shorter runs are years, postcodes, amounts or document references.
        if not 10 <= len(digits) <= 15:
            continue
        if YEAR_PATTERN.fullmatch(digits) or YEAR_RANGE.match(value):
            continue
        return value, snippet(text, value)
    return "", ""


# Page furniture and section headings sit in the same first lines as the name.
# "Page 1 of 4" and "PROFILE SUMMARY" both used to be returned as candidate names.
PAGE_NOISE = re.compile(r"\bpages?\b|\bpage\s*no\b|\bcontinued\b|^\s*\d+\s*$", re.I)
URL_LIKE = re.compile(r"https?://|www\.|\.com\b|\.co\.in\b|linkedin|github", re.I)
NOT_NAME_WORDS = {
    # document furniture
    "resume", "resumé", "cv", "curriculum", "vitae", "biodata", "bio", "data", "page", "no", "of",
    # section headings
    "profile", "summary", "objective", "contact", "details", "personal", "career", "address",
    "email", "mail", "phone", "mobile", "tel", "telephone", "skills", "skill", "education",
    "educational", "experience", "employment", "work", "working", "declaration", "languages",
    "language", "top", "professional", "key", "about", "me", "myself", "qualification",
    "qualifications", "achievements", "strengths", "hobbies", "references", "reference",
    "certifications", "projects", "project", "synopsis", "introduction", "overview",
    # skills-section entries sit in the same column as the name on portal exports
    "technical", "consultation", "competencies", "expertise", "proficiency",
    "highlights", "credentials", "awards", "training", "courses", "interests",
    "undertaken", "areas", "core",
    # job-title words - a designation line is not a name
    "engineer", "manager", "executive", "officer", "director", "consultant", "analyst",
    "developer", "specialist", "head", "lead", "leader", "president", "architect", "supervisor",
    "recruiter", "accountant", "technician", "associate", "intern", "trainee", "senior", "junior",
    "assistant", "deputy", "general", "vice", "chief", "sr", "jr", "avp", "gm", "dgm",
}


def _filename_key(filename: str) -> str:
    """Strip portal prefixes, experience tags and document words from a filename."""
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename or "")
    stem = re.sub(r"^(?:naukri|monster|shine|indeed|linkedin)[_\- ]+", "", stem, flags=re.I)
    stem = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem)          # [27y_0m], (1)
    stem = re.sub(r"\b(?:resume|cv|biodata|profile|final|updated|new|copy|doc)\b", " ", stem, flags=re.I)
    return re.sub(r"[^A-Za-z]+", "", stem).lower()


def _name_from_filename(text: str, filename: str) -> str:
    """Locate the candidate name in the text using the filename as a key.

    CV files are usually named after the candidate, but the filename's spelling
    ("RipunjayKumarSingh", "DEWANGANADKAT") is not what should be exported. So the
    filename is only used to FIND the matching line in the document, and the
    document's own rendering is returned. A filename that matches nothing in the
    text is ignored entirely, so a generic name like "Default.pdf" cannot invent one.
    """
    key = _filename_key(filename)
    if len(key) < 6:
        return ""
    for raw_line in text.splitlines()[:400]:
        line = normalized(raw_line)
        if not line or len(line) > 60 or "@" in line or re.search(r"\d", line):
            continue
        tokens = re.findall(r"[A-Za-z][A-Za-z.'-]*", line)
        if not 1 <= len(tokens) <= 5:
            continue
        if {token.lower().strip(".'-") for token in tokens} & NOT_NAME_WORDS:
            continue
        compact = "".join(tokens).lower().replace(".", "").replace("'", "").replace("-", "")
        if not compact:
            continue
        # The filename may hold only part of the full name ("senthilkumar" for
        # "senthil kumar govindaraj"), so a prefix match counts.
        if compact == key or compact.startswith(key) or key.startswith(compact) and len(compact) >= 6:
            return " ".join(tokens)
    return ""


def find_name(text: str, filename: str = "") -> tuple[str, str, str]:
    """Pick the line in the header block that actually looks like a person's name.

    Returns (name, context, source) where source is "filename" when the candidate
    name was located via the filename and confirmed in the text, "header" when it
    came from ranking the header lines, and "" when nothing was found.

    Scans further than the first few lines because PDF extraction often puts page
    headers, contact blocks and section titles above the name, then ranks the
    surviving candidates: a name usually sits within a line or two of the email or
    phone number, near the top, capitalised, and carries no heading or title words.
    """
    from_filename = _name_from_filename(text, filename)
    if from_filename:
        return from_filename, snippet(text, from_filename), "filename"

    lines = text.splitlines()
    contact_rows = [index for index, line in enumerate(lines[:40])
                    if "@" in line or PHONE_PATTERN.search(line)]

    best_score, best_name, best_line = 0.0, "", ""
    for index, raw_line in enumerate(lines[:30]):
        line = normalized(raw_line)
        if not line or len(line) > 60 or "@" in line:
            continue
        if re.search(r"\d", line) or URL_LIKE.search(line) or PAGE_NOISE.search(line):
            continue
        tokens = re.findall(r"[A-Za-z][A-Za-z.'-]*", line)
        if not 2 <= len(tokens) <= 5:
            continue
        # Reject anything containing a heading or job-title word.
        if {token.lower().strip(".'-") for token in tokens} & NOT_NAME_WORDS:
            continue
        # Real names are capitalised; extracted body prose is not.
        if not all(token[0].isupper() for token in tokens):
            continue

        score = 1.0
        if len(tokens) in (2, 3):
            score += 1.0
        if all(token.isupper() for token in tokens):
            score += 0.5  # ALL-CAPS name banners are common on Indian CVs
        if contact_rows:
            distance = min(abs(index - row) for row in contact_rows)
            if distance <= 3:
                score += 2.0
            elif distance <= 6:
                score += 0.5
        score += max(0.0, (10 - index) * 0.1)  # earlier lines are likelier

        if score > best_score:
            best_score, best_name, best_line = score, " ".join(tokens), line

    return (best_name, snippet(text, best_line), "header") if best_name else ("", "", "")


# A CV names every project city it ever touched. Only one of them is where the
# candidate is, so a region or postcode next to a place name is what marks the
# contact block out from the twenty project sites listed later.
REGION_WORDS = {
    "india", "bharat", "france", "germany", "uae", "u.a.e", "usa", "u.s.a", "uk", "singapore",
    "taiwan", "china", "qatar", "oman", "kuwait", "bahrain", "saudi arabia", "nepal", "bhutan",
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
    "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh",
    "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
    "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
    "west bengal", "delhi", "jammu", "kashmir", "ladakh", "puducherry",
}
REGION_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(w) for w in REGION_WORDS), key=len, reverse=True)) + r")\b", re.I)
PIN_RE = re.compile(r"\b\d{6}\b|\b\d{3}\s\d{3}\b")
LOCATION_LABEL = re.compile(r"(?:current\s+|present\s+|based\s+(?:in|at)\s+)?locations?\s*[:\-]\s*([^\n|]{2,80})", re.I)
_PLACE_NOISE = re.compile(
    r"^(?:at|po|dist|district|city|state|village|post|near|residence|res|permit|mobile|phone|no|"
    r"tel|address|permanent|present|current|location|contact|email|mail|mob|cell|nationality)\b[.:\-]*", re.I)
# A street address is not a location. These words mark the line as one.
_STREET_WORDS = {
    "house", "apartment", "apartments", "apt", "flat", "plot", "road", "rd", "street", "st",
    "lane", "society", "bldg", "building", "tower", "wing", "floor", "sector", "block",
    "opp", "opposite", "behind", "cross", "main", "gali", "marg", "chowk", "complex",
}
# "Old Goa" and "Navi Mumbai" would otherwise be cut down to "Old" and "Navi"
# when the trailing word is also a state name.
_PLACE_QUALIFIER = {"old", "new", "navi", "greater", "north", "south", "east", "west", "upper", "lower"}


def _place_name(value: str) -> str:
    """Reduce an address fragment to the settlement name.

    "Po/Dist.Balangir - 767001" -> "Balangir";  "Erode, Tamil Nadu, India" -> "Erode";
    "Udaipur Rajasthan - 313001 Mobile. No:" -> "Udaipur";  "Old Goa - 403402." -> "Old Goa".
    """
    value = re.split(r"[,|]", value.replace("/", " "))[0]
    value = PIN_RE.sub(" ", value)
    value = re.sub(r"\(.*?\)|[-–—]+.*$|\d+", " ", value)

    parts = []
    for token in normalized(value).split():
        token = _PLACE_NOISE.sub("", token).strip(" .,:-")
        if token:
            parts.append(token)
    # Drop a trailing region word ("Udaipur Rajasthan"), unless what remains is
    # only a direction or size qualifier, which is never a place on its own.
    while len(parts) > 1 and REGION_RE.fullmatch(parts[-1]):
        if parts[-2].lower() in _PLACE_QUALIFIER and len(parts) == 2:
            break
        parts.pop()
    if len(parts) == 1 and REGION_RE.fullmatch(parts[0]):
        parts = []

    name = " ".join(parts[:3]).strip(" .,-")
    if not (2 < len(name) <= 40) or not re.search(r"[A-Za-z]{3}", name):
        return ""
    # Reject leftovers that are punctuation or a street address rather than a place:
    # "Contact +" and "Res Mulla House" both used to survive as locations.
    if re.search(r"[+@#/\\|]|\d", name):
        return ""
    words = {word.lower().strip(".,") for word in name.split()}
    if words & _STREET_WORDS:
        return ""
    # A job title or section heading is not a place. Without this, a line carrying a
    # stray postcode yields values like "DEP TEAM LEADER" or "kV Substation Pakage".
    if words & NOT_NAME_WORDS:
        return ""
    if not all(word[0].isupper() for word in name.split() if word):
        return ""
    return name


def find_locations(text: str) -> list[str]:
    """Return where the candidate is, not everywhere the CV mentions."""
    labelled = LOCATION_LABEL.search(text)
    if labelled:
        place = _place_name(labelled.group(1))
        if place:
            return [place]

    lines = text.splitlines()
    head = lines[:25]
    contact_rows = [index for index, line in enumerate(head) if "@" in line or PHONE_PATTERN.search(line)]

    # A place name carrying a region or postcode, in the header block, is the address.
    best_score, best_place = 0, ""
    for index, raw_line in enumerate(head):
        line = normalized(raw_line)
        if not line or len(line) > 70 or "@" in line:
            continue
        if not (REGION_RE.search(line) or PIN_RE.search(line)):
            continue
        place = _place_name(line)
        if not place:
            continue
        score = 3 if not contact_rows else (5 if min(abs(index - row) for row in contact_rows) <= 3 else 3)
        if score > best_score:
            best_score, best_place = score, place
    if best_place:
        return [best_place]

    # Otherwise fall back to a known city, preferring one stated near the top.
    lower_head = "\n".join(head).lower()
    for location in sorted(LOCATION_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(location)}\b", lower_head):
            return [location.title()]
    lower = text.lower()
    for location in sorted(LOCATION_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(location)}\b", lower):
            return [location.title()]
    return []


def resume_likelihood(text: str) -> tuple[bool, list[str]]:
    lower = text.lower()
    matches = [word for word in ("experience", "education", "employment", "resume", "curriculum vitae", "skills", "qualification") if word in lower]
    has_contact = bool(EMAIL_PATTERN.search(text) or find_phone(text)[0])
    is_resume = (len(matches) >= 2 and has_contact) or len(matches) >= 4
    return is_resume, matches


def supports_value(text: str, value: str) -> bool:
    """Reject LLM values that cannot be traced to the extracted document text."""
    if not value:
        return False
    plain = normalized(value).lower()
    haystack = normalized(text).lower()
    if plain in haystack:
        return True
    tokens = [token for token in re.findall(r"[a-z0-9]{3,}", plain) if token not in {"the", "and", "for", "with"}]
    return bool(tokens) and sum(token in haystack for token in tokens) / len(tokens) >= 0.75

