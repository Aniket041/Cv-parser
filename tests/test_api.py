import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

CV_LINES = [
    "Anita Sharma",
    "Pune, Maharashtra | anita.sharma@example.com | +91 98200 12345",
    "Professional Experience",
    "Senior Data Engineer, Acme Analytics Pvt Ltd",
    "Mar 2021 - Present",
    "Data Analyst, Bright Systems",
    "Jun 2017 - Feb 2021",
    "Education",
    "M.Tech Computer Science, 2017",
    "Total experience: 9 years",
]


def docx_bytes(lines=CV_LINES) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_health_reports_local_dependencies():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["ollama_available"], bool)
    assert "latest_company" in body["fields"]


def test_parse_returns_the_full_record_without_the_model():
    response = client.post("/parse", files={"file": ("Anita Sharma.docx", docx_bytes())},
                           data={"use_llm": "false", "enable_ocr": "false"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Anita Sharma"
    assert body["email"] == "anita.sharma@example.com"
    assert body["latest_company"] == "Acme Analytics Pvt Ltd"
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["processing_status"] in {"Ready", "Needs review"}
    assert "field_confidence" in body["evidence"]


def test_unsupported_file_type_is_rejected():
    response = client.post("/parse", files={"file": ("notes.txt", b"hello")},
                           data={"use_llm": "false"})
    assert response.status_code == 415


def test_empty_upload_is_rejected():
    response = client.post("/parse", files={"file": ("empty.docx", b"")},
                           data={"use_llm": "false"})
    assert response.status_code == 400


def test_parse_text_accepts_already_extracted_text():
    response = client.post("/parse/text", json={"text": "\n".join(CV_LINES),
                                                "filename": "Anita Sharma.docx",
                                                "use_llm": False})
    assert response.status_code == 200
    assert response.json()["name"] == "Anita Sharma"


def test_batch_keeps_going_when_one_document_is_malformed():
    """A broken file must not cost the caller the rest of the batch."""
    files = [
        ("files", ("good.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("broken.docx", b"not a real docx", "application/octet-stream")),
        ("files", ("unsupported.txt", b"plain text", "text/plain")),
    ]
    body = client.post("/parse/batch", files=files, data={"use_llm": "false", "enable_ocr": "false"}).json()
    assert body["total"] == 3
    assert body["parsed"] == 1
    assert body["failed"] == 2
    assert body["results"][0]["ok"] is True
    assert body["results"][1]["ok"] is False and body["results"][1]["error"]
    assert body["results"][2]["ok"] is False


def test_batch_size_is_capped():
    files = [("files", (f"cv{i}.docx", docx_bytes(), "application/octet-stream")) for i in range(101)]
    assert client.post("/parse/batch", files=files, data={"use_llm": "false"}).status_code == 413


@pytest.mark.parametrize("endpoint", ["https://example.com", "http://10.0.0.5:11434"])
def test_a_remote_model_endpoint_is_refused(endpoint):
    """The privacy guarantee must hold through the API, not just the library."""
    body = client.post("/parse/text", json={"text": "\n".join(CV_LINES), "use_llm": True,
                                            "endpoint": endpoint}).json()
    assert "localhost" in body["review_notes"]
