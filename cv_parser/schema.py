"""Shared record shape for the CV parser."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


EXPORT_COLUMNS = [
    "source_file", "processing_status", "name", "email", "phone",
    "total_experience_years", "latest_designation", "latest_company",
    "locations", "qualifications", "qualification_years", "confidence",
    "review_notes",
]


@dataclass
class CandidateRecord:
    source_file: str
    processing_status: str = "Needs review"
    name: str = ""
    email: str = ""
    phone: str = ""
    total_experience_years: str = ""
    latest_designation: str = ""
    latest_company: str = ""
    locations: str = ""
    qualifications: str = ""
    qualification_years: str = ""
    confidence: float = 0.0
    review_notes: str = ""
    file_hash: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def export_dict(self) -> dict[str, Any]:
        return {key: asdict(self)[key] for key in EXPORT_COLUMNS}

    def db_dict(self) -> dict[str, Any]:
        return asdict(self)

