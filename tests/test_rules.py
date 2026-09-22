from cv_parser.education import select_education
from cv_parser.experience import calculated_years, experience_value
from cv_parser.rules import find_email, find_phone, resume_likelihood
from cv_parser.local_llm import LocalModelError, extract_resume_entities
from cv_parser.schema import CandidateRecord
from cv_parser.storage import Storage


SAMPLE = """Asha Patel
asha.patel@example.com | +91 98765 43210 | Location: Pune, Maharashtra
Professional Experience
Senior Data Engineer, Acme Analytics, Jan 2021 - Present
Data Engineer, Beta Systems, Jun 2018 - Dec 2020
Education: B.Tech Computer Science, 2018
Total experience: 6.5 years
Skills: Python, SQL
"""


def test_contact_and_experience_rules():
    assert find_email(SAMPLE)[0] == "asha.patel@example.com"
    assert "98765" in find_phone(SAMPLE)[0]
    assert experience_value(SAMPLE)[0] == "6.5 years"


def test_education_and_resume_detection():
    qualifications = select_education(SAMPLE)
    assert qualifications and "B.Tech" in qualifications[0]["qualification"]
    assert qualifications[0]["year"] == "2018"
    assert resume_likelihood(SAMPLE)[0] is True


def test_overlapping_ranges_are_merged():
    text = "Engineer Jan 2020 - Dec 2022\nConsultant Jun 2022 - Dec 2023"
    # Jan 2020 through Dec 2023 is four years, not the sum of both jobs.
    assert calculated_years(text) == 4.0


def test_llm_client_rejects_remote_endpoints_before_network_call():
    try:
        extract_resume_entities("test", endpoint="https://example.com")
    except LocalModelError as exc:
        assert "localhost" in str(exc)
    else:
        raise AssertionError("A remote endpoint must be rejected")


def test_storage_preserves_editable_records_and_evidence(tmp_path):
    storage = Storage(tmp_path / "parser.db")
    batch = storage.create_batch("Test batch")
    record = CandidateRecord(source_file="candidate.pdf", file_hash="hash", name="Asha", evidence={"name": {"source": "rule"}})
    assert storage.add_record(batch, record) is True
    assert storage.add_record(batch, record) is False
    saved = storage.records(batch)
    saved[0]["name"] = "Reviewed Asha"
    storage.update_records(saved)
    assert storage.records(batch)[0]["name"] == "Reviewed Asha"
    assert storage.evidence(saved[0]["id"])["name"]["source"] == "rule"
