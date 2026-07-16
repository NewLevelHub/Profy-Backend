from app.core.axes import AXIS_CODES
from app.schemas.akinator_question import AkinatorQuestionCreate
from scripts.seed_akinator_content import PROFESSIONS, QUESTIONS, SECTIONS


def test_counts_match_acceptance_criteria():
    assert len(SECTIONS) == 16
    assert len(PROFESSIONS) == 67
    assert len(QUESTIONS) == 41


def test_profession_slugs_are_unique():
    slugs = [p["slug"] for p in PROFESSIONS]
    assert len(slugs) == len(set(slugs))


def test_section_slugs_are_unique():
    slugs = [s["slug"] for s in SECTIONS]
    assert len(slugs) == len(set(slugs))


def test_every_profession_points_to_a_known_section():
    section_slugs = {s["slug"] for s in SECTIONS}
    for prof in PROFESSIONS:
        assert prof["section"] in section_slugs, prof["slug"]


def test_every_profession_has_a_non_empty_profile():
    for prof in PROFESSIONS:
        assert prof["profile"], f"{prof['slug']}: empty profile"


def test_every_profession_profile_uses_valid_axis_codes_and_values():
    for prof in PROFESSIONS:
        for code, value in prof["profile"].items():
            assert code in AXIS_CODES, f"{prof['slug']}: unknown axis '{code}'"
            assert value in (-2, -1, 1, 2), f"{prof['slug']}: bad value {code}={value}"


def test_every_question_passes_schema_and_axis_validation():
    """AC1: 41 AkinatorQuestion entries with valid axis_weights."""
    for q in QUESTIONS:
        AkinatorQuestionCreate.model_validate({**q, "is_active": True})


def test_every_resolves_pair_references_known_professions():
    profession_slugs = {p["slug"] for p in PROFESSIONS}
    for q in QUESTIONS:
        if q["resolves_pair"] is None:
            continue
        for slug in q["resolves_pair"]:
            assert slug in profession_slugs, f"order {q['order']}: unknown profession '{slug}'"


def test_question_orders_are_unique_and_sequential():
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(41))
