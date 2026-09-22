from cv_parser.employment import latest_employment


def test_latest_dates_not_document_order():
    text = 'Work Experience\nEngineer, Beta Systems, Jan 2018 - Dec 2020\nSenior Engineer, Acme Ltd, Jan 2021 - Present\nEducation\nMBA 2023'
    assert latest_employment(text)[:2] == ('Senior Engineer', 'Acme Ltd')


def test_multiline_header():
    text = 'Work Experience\nAcme Technologies\nSenior Project Manager\nJan 2021 - Present'
    assert latest_employment(text)[:2] == ('Senior Project Manager', 'Acme Technologies')


def test_labels_and_role_at_company():
    assert latest_employment('Current designation: General Manager\nCurrent company: Acme')[:2] == ('General Manager', 'Acme')
    assert latest_employment('Software Developer at Acme | Jan 2020 - Dec 2023')[:2] == ('Software Developer', 'Acme')


def test_no_borrowing_company_from_previous_job():
    text = 'Work Experience\nEngineer, Acme Ltd, Jan 2018 - Dec 2020\nDesignation: General Manager\nJan 2021 - Present'
    assert latest_employment(text)[:2] == ('General Manager', '')


def test_education_not_employment():
    assert latest_employment('Education\nMBA Jan 2018 - Dec 2020\nSkills\nProject Manager')[:2] == ('', '')


def test_pipeline_without_ollama_or_ocr(monkeypatch):
    import cv_parser.pipeline as pipeline
    from cv_parser.extractors import ExtractedText
    text = 'Asha Patel\nasha@example.com\nWork Experience\nSenior Engineer, Acme Ltd, Jan 2021 - Present\nEducation\nMBA 2020'
    monkeypatch.setattr(pipeline, 'extract_file', lambda *args: ExtractedText(text, [text]))
    def no_model(*args, **kwargs):
        raise AssertionError('Model must not be called')
    monkeypatch.setattr(pipeline, 'extract_resume_entities', no_model)
    record = pipeline.parse_cv('cv.pdf', b'fixture', use_llm=False, enable_ocr=False)
    assert record.latest_designation == 'Senior Engineer'
    assert record.latest_company == 'Acme Ltd'
    assert record.evidence['latest_company']['source'] == 'rule'


SAMPLE = '''Work Experience (4 years)
NetTech India, Thane, Maharashtra Feb’22 – Present
Working as Business Development Executive
o Market research.
Indus Gartex Pvt. Ltd, Jaipur, Rajasthan Apr’17 – Mar’19
Worked as an HR Executive
Education
MBA-HR 2009 - 2011
Participated in Intra-college group dance competition.
'''


def test_screenshot_sample():
    from cv_parser.experience import experience_value
    assert experience_value(SAMPLE)[0] == '4 years'
    assert latest_employment(SAMPLE)[:2] == ('Business Development Executive', 'NetTech India')


def test_till_date_and_progressive_experience():
    from cv_parser.experience import experience_value
    text = '''HR leader with over 22 years of progressive experience
Professional Experience
ITD Cementation India Limited, Mumbai
November 2015 till date
Designation : Senior Assistant General Manager, Human Resources
'''
    assert experience_value(text)[0] == '22 years'
    assert latest_employment(text)[:2] == ('Senior Assistant General Manager, Human Resources', 'ITD Cementation India Limited')


def test_short_dates_calculate_when_total_absent():
    from cv_parser.experience import calculated_years
    assert calculated_years('Work Experience\nAcme Jan’20 – Dec’20\nBeta Jan 22 - Dec 22') == 2.0


def test_projects_and_activities_rejected():
    from cv_parser.employment import header_fields, invalid_employer
    assert header_fields(['Participated in Intra-college group dance competition.']) == ('', '')
    assert invalid_employer('Project: Construction of Married Accommodations')
    assert invalid_employer('3) Project: Extraction of Construction Drawings')


def test_model_cannot_override_complete_dated_pair(monkeypatch):
    import cv_parser.pipeline as pipeline
    from cv_parser.extractors import ExtractedText
    monkeypatch.setattr(pipeline, 'extract_file', lambda *args: ExtractedText(SAMPLE, [SAMPLE]))
    monkeypatch.setattr(pipeline, 'resume_likelihood', lambda text: (True, []))
    monkeypatch.setattr(pipeline, 'extract_resume_entities', lambda *args, **kwargs: {
        'latest_designation': 'HR Executive', 'latest_company': 'Indus Gartex Pvt. Ltd'})
    record = pipeline.parse_cv('sample.pdf', b'fixture', use_llm=True)
    assert record.latest_designation == 'Business Development Executive'
    assert record.latest_company == 'NetTech India'
    assert record.total_experience_years == '4 years'
