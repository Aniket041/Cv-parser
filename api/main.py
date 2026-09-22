"""HTTP API over the local CV parser.

Binds to 127.0.0.1 by default. Candidate data never leaves the machine: the only
outbound call the parser can make is to Ollama on localhost, and the client
refuses any non-localhost endpoint.

    python -m api                    # http://127.0.0.1:8000, docs at /docs
    python -m api --port 9000
    python -m api --host 0.0.0.0     # exposes PII on the network - see README
"""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from cv_parser import __version__, parse_cv, parse_text
from cv_parser.schema import EXPORT_COLUMNS

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
SUPPORTED_SUFFIXES = (".pdf", ".docx")
MAX_BATCH = 100

app = FastAPI(
    title="Local CV Parser",
    version=__version__,
    description="Offline CV parsing. No cloud API, no API key, no candidate data leaving this machine.",
)


class Candidate(BaseModel):
    """One parsed CV. Mirrors the exported columns, plus evidence."""

    source_file: str
    processing_status: Literal["Ready", "Needs review"]
    name: str = ""
    email: str = ""
    phone: str = ""
    total_experience_years: str = ""
    latest_designation: str = ""
    latest_company: str = ""
    locations: str = ""
    qualifications: str = ""
    qualification_years: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    review_notes: str = ""
    file_hash: str = ""
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-field source, value and supporting text, plus field_confidence scores.",
    )


class BatchItem(BaseModel):
    filename: str
    ok: bool
    candidate: Candidate | None = None
    error: str | None = None


class BatchResult(BaseModel):
    total: int
    parsed: int
    failed: int
    ready: int = Field(0, description="Records that passed the confidence gate and need no review.")
    results: list[BatchItem]


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Already-extracted CV text.")
    filename: str = Field("", description="Original filename. Used as a hint when locating the candidate name.")
    use_llm: bool = True
    model: str = DEFAULT_MODEL
    endpoint: str = DEFAULT_ENDPOINT


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    ollama_available: bool
    ollama_models: list[str]
    ocr_available: bool
    fields: list[str]


def _as_candidate(record) -> Candidate:
    payload = record.db_dict()
    payload["evidence"] = record.evidence
    return Candidate(**payload)


def _check_suffix(filename: str) -> None:
    if not filename.lower().endswith(SUPPORTED_SUFFIXES):
        raise HTTPException(415, f"Only {', '.join(SUPPORTED_SUFFIXES)} are supported, got {filename!r}.")


@app.get("/health", response_model=Health, summary="Service and local dependency status")
def health() -> Health:
    models: list[str] = []
    try:
        with urllib.request.urlopen(f"{DEFAULT_ENDPOINT}/api/tags", timeout=3) as response:
            import json

            models = [m["name"] for m in json.loads(response.read()).get("models", [])]
        ollama_up = True
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        ollama_up = False

    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        ocr = True
    except Exception:
        ocr = False

    return Health(status="ok", version=__version__, ollama_available=ollama_up,
                  ollama_models=models, ocr_available=ocr, fields=EXPORT_COLUMNS)


@app.post("/parse", response_model=Candidate, summary="Parse one PDF or DOCX")
async def parse_one(
    file: Annotated[UploadFile, File(description="A PDF or DOCX CV.")],
    use_llm: Annotated[bool, Form()] = True,
    enable_ocr: Annotated[bool, Form()] = True,
    model: Annotated[str, Form()] = DEFAULT_MODEL,
    endpoint: Annotated[str, Form()] = DEFAULT_ENDPOINT,
) -> Candidate:
    filename = file.filename or "upload"
    _check_suffix(filename)
    content = await file.read()
    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        record = parse_cv(filename, content, enable_ocr=enable_ocr, use_llm=use_llm,
                          model=model, endpoint=endpoint)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    return _as_candidate(record)


@app.post("/parse/batch", response_model=BatchResult, summary="Parse up to 100 files")
async def parse_batch(
    files: Annotated[list[UploadFile], File(description="PDF or DOCX CVs.")],
    use_llm: Annotated[bool, Form()] = True,
    enable_ocr: Annotated[bool, Form()] = True,
    model: Annotated[str, Form()] = DEFAULT_MODEL,
    endpoint: Annotated[str, Form()] = DEFAULT_ENDPOINT,
) -> BatchResult:
    if not files:
        raise HTTPException(400, "No files were uploaded.")
    if len(files) > MAX_BATCH:
        raise HTTPException(413, f"At most {MAX_BATCH} files per request, got {len(files)}.")

    results: list[BatchItem] = []
    for upload in files:
        filename = upload.filename or "upload"
        # One malformed document must not lose the rest of the batch.
        try:
            if not filename.lower().endswith(SUPPORTED_SUFFIXES):
                raise ValueError(f"Unsupported file type: {filename}")
            record = parse_cv(filename, await upload.read(), enable_ocr=enable_ocr,
                              use_llm=use_llm, model=model, endpoint=endpoint)
            results.append(BatchItem(filename=filename, ok=True, candidate=_as_candidate(record)))
        except Exception as exc:
            results.append(BatchItem(filename=filename, ok=False, error=f"{type(exc).__name__}: {exc}"))

    parsed = [item for item in results if item.ok]
    return BatchResult(
        total=len(results), parsed=len(parsed), failed=len(results) - len(parsed),
        ready=sum(1 for item in parsed if item.candidate.processing_status == "Ready"),
        results=results,
    )


@app.post("/parse/text", response_model=Candidate, summary="Parse already-extracted text")
def parse_raw_text(request: TextRequest) -> Candidate:
    record = parse_text(request.filename or "text", request.text, use_llm=request.use_llm,
                        model=request.model, endpoint=request.endpoint)
    return _as_candidate(record)
