"""Regressions found by parsing a real batch, not by the labelled eval set."""
from cv_parser.employment import header_fields, invalid_employer
from cv_parser.extractors import clean_text


def test_pdf_bullet_glyphs_are_stripped_from_extracted_text():
    """Wingdings bullets survive PDF extraction as Private Use Area code points
    and used to be exported glued to the value: " Deputy General Manager"."""
    assert clean_text(" Deputy General Manager").strip() == "Deputy General Manager"
    assert clean_text(" Lodha Group (Lower Parel)").strip() == "Lodha Group (Lower Parel)"
    assert clean_text("� Asst. Manager").strip() == "Asst. Manager"
    assert clean_text("Normal text, unchanged") == "Normal text, unchanged"


def test_a_label_ending_in_a_full_stop_is_still_a_label():
    """"Designation. Sr. Manager (liaison)" exported the label along with the value."""
    assert header_fields(["Designation. Sr. Manager (liaison)"])[0] == "Sr. Manager (liaison)"
    assert header_fields(["Designation : Project Manager"])[0] == "Project Manager"


def test_a_department_name_is_not_an_employer():
    """"Contracts" and "Tendering" were exported as the candidate's company."""
    assert invalid_employer("Contracts")
    assert invalid_employer("Tendering")
    assert invalid_employer("Planning")
    assert not invalid_employer("Tata Projects Limited")
    assert not invalid_employer("SMEC -India Pvt Ltd")
    assert not invalid_employer("KEC International Ltd")
