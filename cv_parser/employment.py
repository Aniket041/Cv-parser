"""Conservative employment header parsing without a model."""
import re
from datetime import date

from .experience import RANGE, STOP, month_index, normalize_work_text

TITLE = re.compile(r"\b(?:engineer|manager|consultant|developer|analyst|officer|executive|director|president|head|lead|specialist|architect|accountant|recruiter|supervisor|technician|associate|intern|CEO|CFO|CTO|COO)\b", re.I)
COMPANY = re.compile(r"\b(?:limited|ltd|pvt|private|inc|llp|llc|corporation|corp|technologies|solutions|systems|services|industries|bank|group|construction|analytics)\b", re.I)
ROLE_LABEL = re.compile(r"^(?:(?:current|latest|present)\s+)?(?:designation|job title|position|role)\s*[:\-.]\s*(.+)$", re.I)
COMPANY_LABEL = re.compile(r"^(?:(?:current|latest|present)\s+)?(?:company(?: name)?|employer|organization|organisation)\s*[:\-.]\s*(.+)$", re.I)
# Department and function names arrive via "Department : Contracts" style labels and
# read like one-word employers. An employer needs more than a function name.
DEPARTMENT_WORDS = {
    "contracts", "contract", "tendering", "tenders", "procurement", "planning", "billing",
    "administration", "admin", "operations", "execution", "finance", "accounts", "hr",
    "human resources", "quality", "safety", "design", "engineering", "projects", "project",
    "sales", "marketing", "purchase", "stores", "logistics", "maintenance", "production",
}
BOUNDARY = re.compile(r"^(?:professional experience|work experience|employment history|career history|experience|education|academic|skills|projects|responsibilities|achievements)\s*:?$", re.I)
# Field labels that introduce something other than an employer. Their leftover
# text ("Duration : Since") must never be adopted as a company name.
LABEL_SKIP = re.compile(r"^(?:client|consultant|project|period|duration|key role|duties|nature of project)\s*[:\-]", re.I)


def clean(value: str) -> str:
    value = value.strip(" \t,;|:-–—•")
    while value.endswith(')') and value.count(')') > value.count('('):
        value = value[:-1].rstrip()
    while value.startswith('(') and value.count('(') > value.count(')'):
        value = value[1:].lstrip()
    return value


_COMMA_HOLD = "\x00"


def split_header(line: str) -> list[str]:
    """Split a header into role/company parts without cutting inside brackets.

    "Business Head (Power Transmission, Substation & Distribution)" is one role,
    not a role plus a company called "Substation & Distribution".
    """
    depth, protected = 0, []
    for char in line:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        protected.append(_COMMA_HOLD if (char == "," and depth) else char)
    parts = re.split(r"\s+(?:at|with)\s+|\s*[@|,;]\s*|\s+[-–—]\s+", "".join(protected))
    return [part.replace(_COMMA_HOLD, ",") for part in parts]


def invalid_employer(value: str) -> bool:
    if re.search(r"\bproject\s*:|\b(?:participated|responsibilities|achievements|extraction of|construction of|worked as|working as|managed|handled|coordinated|improved|developed|awards|competition)\b", value, re.I):
        return True
    # "Contracts" and "Tendering" are the department, not who employs the candidate.
    bare = re.sub(r"[^\w\s]", " ", value or "").strip().lower()
    return bool(bare) and len(bare.split()) <= 2 and bare in DEPARTMENT_WORDS


def header_fields(lines: list[str]) -> tuple[str, str]:
    role = company = ""
    for line in lines:
        line = clean(RANGE.sub("", line))
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if not line or len(line) > 180 or STOP.search(line) or BOUNDARY.match(line):
            continue
        working = re.match(r"^(?:working|worked|employed|serving)\s+as\s+(?:an?\s+)?(.+)$", line, re.I)
        if working:
            role = role or clean(working[1])
            continue
        if invalid_employer(line) or re.match(r"^\d+\)", line):
            continue
        role_match, company_match = ROLE_LABEL.match(line), COMPANY_LABEL.match(line)
        if role_match:
            role = clean(role_match[1])
            continue
        if company_match:
            company = clean(company_match[1])
            continue
        if LABEL_SKIP.match(line):
            continue
        parts = [clean(part) for part in split_header(line) if clean(part)]
        title_parts = [part for part in parts if TITLE.search(part) and len(part.split()) <= 12]
        if title_parts:
            role = role or title_parts[0]
            other = [part for part in parts if part not in title_parts]
            if other:
                company = company or next((part for part in other if COMPANY.search(part)), other[0])
        elif COMPANY.search(line) and len(line.split()) <= 14:
            company = company or next((part for part in parts if COMPANY.search(part)), parts[0])
    if company:
        company = re.split(r"\s+on payroll of\s+", company, flags=re.I)[0].strip()
        company = re.sub(r"^M/s\s+", "", company, flags=re.I)
    return role, company


def latest_employment(text: str) -> tuple[str, str, str]:
    lines = [line.strip() for line in normalize_work_text(text).splitlines() if re.search(r"[A-Za-z0-9]", line)]
    dated = [(index, match) for index, line in enumerate(lines) for match in RANGE.finditer(line)]
    candidates = []
    for ordinal, (index, match) in enumerate(dated):
        start, end = month_index(match[1]), month_index(match[2], True)
        now = date.today().year * 12 + date.today().month - 1
        if start is None or end is None or start > end or end > now:
            continue
        if STOP.search(lines[index]):
            continue
        # A header may be on the date line or immediately before it. Never cross
        # another dated entry or a section boundary when collecting its fields.
        lower = dated[ordinal - 1][0] + 1 if ordinal else 0
        before = []
        for previous in range(index - 1, max(lower, index - 6) - 1, -1):
            if BOUNDARY.match(lines[previous]) or STOP.search(lines[previous]):
                break
            before.insert(0, lines[previous])
            if COMPANY_LABEL.match(lines[previous]) or (COMPANY.search(lines[previous]) and not invalid_employer(lines[previous])):
                break
        block = before + [lines[index]]
        role, company = header_fields([lines[index]])
        if not (role and company):
            role, company = header_fields(block)
        # Date-first headers: only use following lines when the date had no
        # preceding header, to avoid borrowing fields from a later employer.
        if not role or not company:
            upper = dated[ordinal + 1][0] if ordinal + 1 < len(dated) else len(lines)
            after = []
            for following in range(index + 1, min(upper, index + 3)):
                if BOUNDARY.match(lines[following]) or STOP.search(lines[following]):
                    break
                after.append(lines[following])
            for next_line in after:
                if re.match(r"^(?:working|worked|employed|serving)\s+as\b", next_line, re.I) or ROLE_LABEL.match(next_line):
                    next_role, _ = header_fields([next_line])
                    role = role or next_role
                    block.append(next_line)
                    # A named employer without a corporate suffix (NetTech India)
                    # can be identified by the dated header followed by 'Working as'.
                    if not company:
                        header = clean(RANGE.sub("", lines[index]))
                        if not header and before:
                            header = before[-1]
                        if (header and not invalid_employer(header) and not BOUNDARY.match(header)
                                and not STOP.search(header) and not TITLE.search(header)
                                and not LABEL_SKIP.match(header)):
                            company = clean(header.split(',')[0])
                    break
            if not role and not company:
                block = [lines[index]] + after
                role, company = header_fields(block)
            # A header may name the role above the date and the employer below it.
            # Only a line that actually reads like an employer is accepted here.
            if role and not company:
                for next_line in after:
                    candidate = clean(RANGE.sub("", next_line))
                    labelled = COMPANY_LABEL.match(candidate)
                    if labelled:
                        company = clean(labelled[1])
                        block.append(next_line)
                        break
                    if (candidate and not LABEL_SKIP.match(candidate) and not invalid_employer(candidate)
                            and not BOUNDARY.match(candidate) and not STOP.search(candidate)
                            and not TITLE.search(candidate) and COMPANY.search(candidate)
                            and len(candidate.split()) <= 14):
                        company = candidate
                        block.append(next_line)
                        break
        if role or company:
            candidates.append((end, start, role, company, "\n".join(block)))
    if candidates:
        _, _, role, company, evidence = max(candidates, key=lambda item: item[:2])
        return role, company, evidence
    # Explicitly labelled current details work even if the CV omits dates.
    current = [line for line in lines if re.match(r"^(?:current|latest|present)\s+", line, re.I)]
    role, company = header_fields(current)
    return role, company, "\n".join(current)
