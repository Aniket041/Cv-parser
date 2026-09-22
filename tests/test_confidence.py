from cv_parser.confidence import CRITICAL, field_scores, is_ready, overall, values_agree


def complete_signals(**overrides):
    signals = {
        "name": "Asha Patel", "name_from_filename": True,
        "email": "asha@example.com", "phone": "+91 9000000003",
        "total_experience_years": "8 years", "experience_stated": True,
        "latest_designation": "Project Manager", "latest_company": "Acme Ltd",
        "employment_agreement": {"latest_designation": "agree", "latest_company": "agree"},
        "locations": ["Pune"],
        "qualifications": "MBA", "qualification_year": True,
    }
    signals.update(overrides)
    return signals


def test_agreement_between_extractors_beats_a_single_source():
    agreed = field_scores(complete_signals())
    alone = field_scores(complete_signals(employment_agreement={}))
    assert agreed["latest_company"] > alone["latest_company"]
    assert overall(agreed) > overall(alone)


def test_conflicting_extractors_score_below_the_ready_floor():
    scores = field_scores(complete_signals(
        employment_agreement={"latest_designation": "conflict", "latest_company": "conflict"}))
    assert scores["latest_company"] < 0.5
    assert not is_ready(scores, overall(scores), blocking=False)


def test_missing_critical_field_blocks_ready_however_good_the_rest_is():
    for field in CRITICAL:
        signals = complete_signals()
        signals[field] = "" if field != "total_experience_years" else ""
        scores = field_scores(signals)
        assert not is_ready(scores, overall(scores), blocking=False), field


def test_populated_but_unsupported_values_do_not_reach_the_old_high_score():
    """A record filled entirely by weak single-source guesses must not look confident.

    The previous score counted populated fields, so this case scored 0.95.
    """
    scores = field_scores(complete_signals(
        name_from_filename=False, experience_stated=False,
        employment_agreement={}, qualification_year=False))
    assert overall(scores) < 0.75
    assert not is_ready(scores, overall(scores), blocking=False)


def test_ocr_and_non_resume_text_cannot_be_ready():
    scores = field_scores(complete_signals())
    assert is_ready(scores, overall(scores), blocking=False)
    assert not is_ready(scores, overall(scores, used_ocr=True), blocking=True)
    assert overall(scores, is_resume=False) < overall(scores)


def test_values_agree_ignores_punctuation_and_legal_suffixes():
    assert values_agree("CAPACITE INFRAPROJECTS LTD", "Capacite Infraprojects")
    assert values_agree("Acme Analytics Pvt Ltd", "Acme Analytics Private Limited")
    assert not values_agree("Montecarlo Limited", "Torrent Power Limited")
    assert not values_agree("", "Acme Ltd")
