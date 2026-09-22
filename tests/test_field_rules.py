from cv_parser.experience import experience_value
from cv_parser.rules import _place_name, find_locations, find_name, find_phone


def test_year_range_is_not_a_phone_number():
    """"2012-2016" has eight digits and used to be exported as a phone number."""
    assert find_phone("Graduation 2012-2016 affiliated to R.G.P.V. Bhopal")[0] == ""
    assert find_phone("Worked 2019 - 2024 at Acme")[0] == ""


def test_phone_requires_a_full_subscriber_number():
    assert find_phone("PIN 411057")[0] == ""
    assert find_phone("Invoice 12345678")[0] == ""
    assert find_phone("Mobile 9000000004")[0] == "9000000004"
    assert find_phone("Contact: +91-9000000005")[0] == "+91-9000000005"


def test_stated_total_survives_adjectives_between_years_and_experience():
    """Real CVs pad the phrase; the stated total must still beat computed dates."""
    assert experience_value("25 years of rich & extensive experience in project execution")[0] == "25 years"
    assert experience_value("Having 4+ years of extensive experience as a full stack developer")[0] == "4+ years"
    assert experience_value("12 + years of experience in IT performing Software Architecture")[0] == "12+ years"


def test_padding_does_not_let_the_match_cross_a_sentence():
    assert experience_value("He stayed 3 years. Later he gained experience abroad.")[0] == ""


def test_name_is_not_taken_from_page_furniture_or_headings():
    for line in ("Page 1 of 4", "PAGE NO 01 OF 03", "PROFILE SUMMARY",
                 "www.linkedin.com/in/someone", "Technical Consultation"):
        text = f"{line}\nSome body text here\nasha@example.com"
        assert find_name(text)[0] != " ".join(line.split()), line


def test_name_located_via_filename_returns_the_documents_own_spelling():
    text = "PAGE NO 01 OF 03\nProfile Summary\nRAVINDRA KUMAR SINHA\nGENERAL MANAGER\nravindra@example.com"
    name, _, source = find_name(text, "Naukri_RavindraKumarSinha[27y_0m].pdf")
    assert name == "RAVINDRA KUMAR SINHA"
    assert source == "filename"


def test_address_fragments_reduce_to_the_settlement_name():
    assert _place_name("Erode, Tamil Nadu, India") == "Erode"
    assert _place_name("Po/Dist.Balangir - 767001") == "Balangir"
    assert _place_name("Udaipur Rajasthan -   313001") == "Udaipur"
    assert _place_name("Manosque, France (Residence Permit)") == "Manosque"
    assert _place_name("India") == ""


def test_a_qualifier_is_never_left_stranded_by_region_stripping():
    """"Old Goa" must not become "Old" just because Goa is also a state."""
    assert _place_name("Old Goa - 403402.") == "Old Goa"
    assert _place_name("Navi Mumbai, Maharashtra") == "Navi Mumbai"


def test_locations_is_where_the_candidate_is_not_every_city_named():
    text = (
        "ARJUN MEHTA\n12 Example Road, South Dumdum,\nKolkata- 700074\n"
        "arjun.mehta@example.com\n9000000001\n\n"
        "Delivered projects in Pune, Mumbai, Chennai, Bangalore and Hyderabad.\n"
    )
    assert find_locations(text) == ["Kolkata"]


def test_contact_and_street_lines_are_not_locations():
    """Both survived as locations in a real batch: "Contact +" and "Res Mulla House"."""
    assert _place_name("Contact +91-9000000002") == ""
    assert _place_name("Res. Mulla House, Mumbai - 400001") == ""
    assert _place_name("174 Ghosh Para Road, South Dumdum") == ""


def test_job_titles_near_a_postcode_are_not_locations():
    """A stray postcode on a heading line yielded "DEP TEAM LEADER" as a location."""
    assert _place_name("DEP TEAM LEADER 400001") == ""
    assert _place_name("kV Substation Pakage 110001") == ""


def test_an_explicit_location_label_wins():
    text = "Rohit Kulkarni\nCurrent Location- Udaipur Rajasthan - 313001\nWorked in Indore and Jabalpur"
    assert find_locations(text) == ["Udaipur"]


def test_filename_cannot_invent_a_name_absent_from_the_text():
    text = "Page 1 of 2\nSome unrelated document body\ninfo@example.com"
    name, _, source = find_name(text, "Naukri_SomebodyElseEntirely[10y_0m].pdf")
    assert source != "filename"
    assert "Somebody" not in name
