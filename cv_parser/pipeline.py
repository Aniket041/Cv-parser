"""Hybrid local CV parsing pipeline."""
from __future__ import annotations

import hashlib
from typing import Any

from .extractors import extract_file
from .local_llm import LocalModelError, extract_resume_entities
from .rules import (find_email, find_locations, find_name, find_phone,
                    resume_likelihood, snippet, supports_value)
from .confidence import CRITICAL, READY_FLOOR, field_scores, is_ready, overall, values_agree
from .schema import CandidateRecord
from .education import select_education
from .experience import experience_value
from .employment import latest_employment, invalid_employer


def _evidence(source: str, value: str, context: str) -> dict[str, str]:
    return {"source": source, "value": value, "context": context}


def parse_cv(filename: str, content: bytes, *, enable_ocr: bool = True, use_llm: bool = True,
             model: str = "qwen2.5:3b", endpoint: str = "http://127.0.0.1:11434") -> CandidateRecord:
    """Parse a PDF or DOCX file into a candidate record."""
    extracted = extract_file(filename, content, enable_ocr)
    return parse_text(filename, extracted.text,
                      file_hash=hashlib.sha256(content).hexdigest(),
                      used_ocr=extracted.used_ocr, warnings=extracted.warnings,
                      use_llm=use_llm, model=model, endpoint=endpoint)


def parse_text(filename: str, text: str, *, file_hash: str = "", used_ocr: bool = False,
               warnings: list[str] | None = None, use_llm: bool = True,
               model: str = "qwen2.5:3b", endpoint: str = "http://127.0.0.1:11434") -> CandidateRecord:
    """Parse already-extracted CV text.

    Use this when the caller has the text already and does not want the file read
    again, for example a service that stores extracted text alongside the original.
    """
    if not file_hash:
        file_hash = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    record = CandidateRecord(source_file=filename, file_hash=file_hash)
    warnings = list(warnings or [])
    if not (text or "").strip():
        record.review_notes = ("No readable text was extracted. " + " ".join(warnings)).strip()
        return record

    email, email_context = find_email(text)
    phone, phone_context = find_phone(text)
    name, name_context, name_source = find_name(text, filename)
    experience, experience_context = experience_value(text)
    locations = find_locations(text)
    qualifications = select_education(text)
    is_resume, resume_terms = resume_likelihood(text)
    evidence: dict[str, Any] = {
        "email": _evidence("rule", email, email_context),
        "phone": _evidence("rule", phone, phone_context),
        "name": _evidence("rule", name, name_context),
        "total_experience_years": _evidence("rule", experience, experience_context),
        "locations": _evidence("rule", "; ".join(locations), snippet(text, locations[0]) if locations else ""),
        "qualifications": _evidence("rule", "; ".join(q["qualification"] for q in qualifications), "Degree/education lines"),
    }

    llm_result: dict[str, Any] = {}
    if use_llm and is_resume:
        try:
            llm_result = extract_resume_entities(text, model=model, endpoint=endpoint)
        except LocalModelError as exc:
            warnings.append(str(exc))

    for field in ("name", "latest_designation", "latest_company"):
        candidate = str(llm_result.get(field, "")).strip()
        if candidate and supports_value(text, candidate):
            if field != "name" or not name:
                if field == "name":
                    name = candidate
                evidence[field] = _evidence("local_llm", candidate, snippet(text, candidate))

    # The field holds where the candidate is, so the model's list of every place
    # named in the CV is only consulted when the rules found no address at all.
    llm_locations = llm_result.get("locations", [])
    if not locations and isinstance(llm_locations, list):
        for value in llm_locations:
            value = str(value).strip()
            if value and supports_value(text, value):
                locations.append(value)
                break
    # Select directly from source education entries. Model output cannot attach a
    # year merely because that year appears somewhere else in the document.
    evidence["qualifications"] = _evidence(
        "rule", qualifications[0]["qualification"] if qualifications else "",
        qualifications[0]["context"] if qualifications else "")
    evidence["qualification_years"] = _evidence(
        "rule", qualifications[0]["year"] if qualifications else "",
        qualifications[0]["context"] if qualifications else "")
    if qualifications and not qualifications[0]["year"]:
        warnings.append("Passing year for the selected qualification was not found; verify it manually.")

    designation = str(llm_result.get("latest_designation", "")).strip()
    company = str(llm_result.get("latest_company", "")).strip()
    if designation and not supports_value(text, designation):
        designation = ""
    if company and (not supports_value(text, company) or invalid_employer(company)):
        company = ""

    llm_designation, llm_company = designation, company
    employment_source = "local_llm"
    employment_context = ""
    rule_role, rule_company, rule_context = latest_employment(text)
    # Prefer a complete dated pair; do not mix employers between sources.
    if (rule_role and rule_company) or (not designation and not company):
        designation, company = rule_role, rule_company
        employment_source, employment_context = "rule", rule_context

    # The two extractors ran independently, so whether they landed on the same
    # employer is real evidence about the answer rather than a restatement of it.
    employment_agreement: dict[str, str] = {}
    for field, from_rule, from_llm in (("latest_designation", rule_role, llm_designation),
                                       ("latest_company", rule_company, llm_company)):
        if from_rule and from_llm:
            employment_agreement[field] = "agree" if values_agree(from_rule, from_llm) else "conflict"
    if not designation or not company:
        warnings.append("Latest designation/company could not both be identified; review employment details.")

    record.name, record.email, record.phone = name, email, phone
    record.total_experience_years = experience
    record.latest_designation, record.latest_company = designation, company
    record.locations = "; ".join(locations)
    record.qualifications = "; ".join(item["qualification"] for item in qualifications)
    record.qualification_years = "; ".join(item["year"] for item in qualifications)
    evidence["latest_designation"] = _evidence(employment_source, designation, employment_context or snippet(text, designation))
    evidence["latest_company"] = _evidence(employment_source, company, employment_context or snippet(text, company))
    record.evidence = evidence

    scores = field_scores({
        "name": name, "name_from_filename": name_source == "filename",
        "email": email, "phone": phone,
        "total_experience_years": experience,
        "experience_stated": bool(experience) and not experience_context.startswith("Calculated"),
        "latest_designation": designation, "latest_company": company,
        "employment_agreement": employment_agreement,
        "locations": locations,
        "qualifications": record.qualifications,
        "qualification_year": bool(record.qualification_years.strip()),
    })
    record.confidence = overall(scores, used_ocr=used_ocr, is_resume=is_resume)
    record.evidence["field_confidence"] = {field: round(score, 2) for field, score in scores.items()}

    if not is_resume:
        warnings.insert(0, f"Likely not a CV (resume signals: {', '.join(resume_terms) or 'none'}).")
    if used_ocr:
        warnings.append("Text was extracted using OCR; verify fields carefully.")
    conflicts = [field for field, state in employment_agreement.items() if state == "conflict"]
    if conflicts:
        warnings.append("Rules and the local model disagree on " +
                        ", ".join(field.replace("latest_", "") for field in conflicts) + "; verify against the CV.")
    weak = [field for field in CRITICAL if scores.get(field, 0.0) < READY_FLOOR]
    if weak:
        warnings.append("Low-confidence or missing: " + ", ".join(weak) + ".")
    if is_ready(scores, record.confidence, blocking=not is_resume or used_ocr):
        record.processing_status = "Ready"
    record.review_notes = " ".join(warnings) or ("Review missing or low-confidence fields." if record.processing_status != "Ready" else "")
    return record
