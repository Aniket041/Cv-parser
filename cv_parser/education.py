"""Select one completed degree and its own passing year."""
import re
from datetime import date

DEGREES = re.compile(
    r"(?<!\w)(?:Ph\.?\s?D\.?|doctorate|M\.?\s?B\.?\s?A\.?|M\.?\s?M\.?\s?S\.?|"
    r"[BM]\.\s?(?:Tech|Sc|Com)\.?|[BM](?:Tech|Sc|Com)|[BM]\.?\s?C\.?A\.?|BBA|"
    r"B\.\s?E\.?|M\.\s?E\.?|BE|ME|PGDM|PGDBM|"
    r"bachelor(?:'s)?(?: of [A-Za-z ]+)?|master(?:'s)?(?: of [A-Za-z ]+)?|"
    r"post\s*graduate diploma|diploma|HSC|SSC)(?!\w)", re.I)
PENDING = re.compile(r"pursuing|ongoing|in progress|expected|not completed|discontinued", re.I)


def rank_degree(value: str) -> int:
    compact = re.sub(r"[^a-z]", "", value.lower())
    if compact.startswith(("phd", "doctorate")):
        return 6
    if compact.startswith(("mba", "mms", "mtech", "msc", "mcom", "mca", "master", "pgdm", "pgdbm", "postgraduate")) or compact == "me":
        return 5
    if compact.startswith(("btech", "bsc", "bcom", "bca", "bba", "bachelor")) or compact == "be":
        return 4
    return {"diploma": 3, "hsc": 2, "ssc": 1}.get(compact, 0)


def select_education(text: str) -> list[dict[str, str]]:
    candidates = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        matches = list(DEGREES.finditer(line))
        for position, match in enumerate(matches):
            token = match.group().strip().rstrip(".")
            # Bare English 'be' and 'me' must never be interpreted as degrees.
            if token.lower() in {"be", "me"} and token not in {"BE", "ME"}:
                continue
            end = matches[position + 1].start() if position + 1 < len(matches) else len(line)
            block = line[match.start():end]
            # PDF degree and year often occur on separate lines. Stop at the next degree/section.
            if len(matches) == 1:
                for following in lines[index + 1:index + 4]:
                    if DEGREES.search(following) or re.search(r"experience|employment|skills|projects|company", following, re.I):
                        break
                    if re.search(r"\b(?:19|20)\d{2}\b", block):
                        break
                    block += "\n" + following
            if PENDING.search(block):
                continue
            years = re.findall(r"\b(?:19|20)\d{2}\b", block)
            short_range = re.search(r"\b((?:19|20)\d{2})\s*[-–/]\s*(\d{2})\b", block)
            if short_range:
                years.append(short_range[1][:2] + short_range[2])
            year = max(years, default="")
            if year and int(year) > date.today().year:
                continue
            candidates.append({"qualification": token, "year": year, "context": block.strip(), "rank": rank_degree(token)})
    if not candidates:
        return []
    best = max(candidates, key=lambda item: (item["rank"], int(item["year"] or 0)))
    return [{key: str(best[key]) for key in ("qualification", "year", "context")}]
