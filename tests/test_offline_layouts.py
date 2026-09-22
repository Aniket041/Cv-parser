from cv_parser.employment import latest_employment
from cv_parser.experience import calculated_years, experience_value


def test_company_not_project_or_location():
    text = '''Professional Journey:
New Delhi, M/s NKG Infrastructure Ltd - India
Role: Project Coordinator
Project: Construction of Married Accn incl allied services
for Indian Armed forces
February 2024 - till date
'''
    assert latest_employment(text)[:2] == ('Project Coordinator', 'NKG Infrastructure Ltd')


def test_period_labels_blank_lines_and_practical_experience():
    text = '''13 years of Practical experience
CURRENT EXPERIENCE
Company : SMEC -India Pvt Ltd
Period : March 2020 to Till Date

Designation : Senior Interface Engineer
Client : Chennai Metro Rail Limited
'''
    assert experience_value(text)[0] == '13 years'
    assert latest_employment(text)[:2] == ('Senior Interface Engineer', 'SMEC -India Pvt Ltd')


def test_date_range_wrapped_onto_next_line():
    text = '''Work Experience
1. Senior Engineer, Kalpataru Projects International Limited | May 2023 to
till date
'''
    assert latest_employment(text)[:2] == ('Senior Engineer', 'Kalpataru Projects International Limited')
    assert calculated_years(text) is not None


def test_company_parentheses_preserved():
    text = 'Quant Risk Manager, NatWest Markets (RBS), Gurgaon (Jan 2019 - present):'
    assert latest_employment(text)[:2] == ('Quant Risk Manager', 'NatWest Markets (RBS)')


def test_no_dates_from_blank_line_education_section():
    text = 'Education\n\nMBA Jan 2016 - Dec 2017\nWork Experience\n\nEngineer, Acme\n\nJan 2020 - Dec 2020'
    assert calculated_years(text) == 1.0


def test_split_role_label():
    text = 'Experience\nAcme Ltd\nJan 2020 - Present\nPosition\n\n: HR Manager'
    assert latest_employment(text)[:2] == ('HR Manager', 'Acme Ltd')
