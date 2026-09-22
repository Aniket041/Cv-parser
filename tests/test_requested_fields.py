from cv_parser.education import select_education
from cv_parser.experience import experience_value, calculated_years


def test_highest_degree_and_own_end_year():
    result = select_education("Education\nB.Com Accounting 2013\nMMS Finance 2014-16\nDiploma 2021")
    assert result[0]['qualification'] == 'MMS'
    assert result[0]['year'] == '2016'
    assert len(result) == 1


def test_prose_and_awards_are_not_degrees():
    assert select_education('be associated with a progressive organization\nme for this; me. I can be\nBest of Best Award 2020') == []


def test_pending_master_does_not_replace_completed_bachelor():
    result = select_education('B.Tech 2018\nMBA pursuing')
    assert result[0]['qualification'] == 'B.Tech'
    assert result[0]['year'] == '2018'


def test_missing_year_not_borrowed_from_next_degree():
    result = select_education('MBA\nB.Com 2013')
    assert result[0]['qualification'] == 'MBA'
    assert result[0]['year'] == ''


def test_latest_of_equal_degrees():
    assert select_education('M.Sc 2015\nMBA 2020')[0]['year'] == '2020'


def test_explicit_years_months_override_dates():
    value, _ = experience_value('Overall experience: 8 years 6 months\nWork Experience\nAcme Jan 2020 - Dec 2021')
    assert value == '8 years 6 months'
    assert experience_value('12+ years of professional experience')[0] == '12+ years'


def test_calculation_excludes_education_and_merges_jobs():
    text = 'Education\nB.Tech Jan 2010 - Dec 2013\nWork Experience\nAcme Jan 2020 - Dec 2022\nBeta Jun 2022 - Dec 2023\nEducation\nMBA Jan 2024 - Dec 2025'
    assert calculated_years(text) == 4.0


def test_numeric_dates_gaps_and_no_employment():
    assert calculated_years('Employment\nAcme 01/2020 - 12/2020\nBeta 01/2022 - 12/2022') == 2.0
    assert calculated_years('Education\nB.Tech Jan 2010 - Dec 2013') is None


def test_pipeline_rejects_llm_education_year_cross_association(monkeypatch):
    import cv_parser.pipeline as pipeline
    from cv_parser.extractors import ExtractedText
    text = 'Asha Patel\nasha@example.com\nEducation\nMBA\nB.Com 2013\nSkills Python\nTotal experience: 8 years 6 months'
    monkeypatch.setattr(pipeline, 'extract_file', lambda *args: ExtractedText(text, [text]))
    monkeypatch.setattr(pipeline, 'extract_resume_entities', lambda *args, **kwargs: {
        'qualifications': [{'qualification': 'MBA', 'year': '2013'}]})
    record = pipeline.parse_cv('cv.pdf', b'fixture')
    assert record.qualifications == 'MBA'
    assert record.qualification_years == ''
    assert record.total_experience_years == '8 years 6 months'
    assert record.processing_status == 'Needs review'
    assert record.evidence['qualifications']['value'] == 'MBA'
