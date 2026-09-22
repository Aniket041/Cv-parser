"""Offline CV parsing.

Everything runs on the local machine. The only network call the package can make
is to Ollama on localhost, and the client refuses any non-localhost endpoint.

Library use:

    from cv_parser import parse_cv

    record = parse_cv("candidate.pdf", pdf_bytes, use_llm=True)
    record.name, record.latest_company, record.confidence
    record.export_dict()          # the thirteen exported columns
    record.evidence               # per-field source, value, context and confidence

HTTP use: see `api/` and `python -m api`.
"""
from .confidence import field_scores, is_ready, overall
from .extractors import ExtractedText, extract_file
from .local_llm import LocalModelError
from .pipeline import parse_cv, parse_text
from .schema import EXPORT_COLUMNS, CandidateRecord
from .storage import Storage

__version__ = "1.0.0"

__all__ = [
    "parse_cv",
    "parse_text",
    "CandidateRecord",
    "EXPORT_COLUMNS",
    "LocalModelError",
    "ExtractedText",
    "extract_file",
    "Storage",
    "field_scores",
    "is_ready",
    "overall",
    "__version__",
]
