"""Contract tests for the student-facing v2 response schema
(app/schemas/result_v2.py) — pure Pydantic validation, no DB, no LLM,
independent of tests/unit/test_admin_result_schema.py (the raw/admin
contract's own, separate test file — the one cross-check here only compares
field *names*, it never imports admin fixtures or shares state).

The point of this file: report_v2_assembler.py is already covered by
tests/unit/test_report_v2_assembler.py (assembler *builds* the right
shape), but nothing yet proved the *schema itself* rejects an impossible
shape if some other/future caller built it wrong. These tests construct
the models directly, bypassing the assembler entirely.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.admin_result import AdminAnalysisResultResponse
from app.schemas.result_v2 import (
    DISCLAIMER,
    MiResultResponse,
    ResultV2Adapter,
    RiasecResultResponse,
    StudentCareer,
    StudentInterestMapItem,
    StudentStrengthCard,
    StudentThinkingStyleNote,
)

_NOW = datetime.now(timezone.utc)


def _strength_card(i: int = 0) -> StudentStrengthCard:
    return StudentStrengthCard(title=f"Сильная сторона {i}", description="Короткое описание")


def _thinking_note(i: int = 0) -> StudentThinkingStyleNote:
    return StudentThinkingStyleNote(title=f"Стиль {i}", description="Короткое описание")


def _interest_items(codes: list[str]) -> list[StudentInterestMapItem]:
    return [StudentInterestMapItem(code=c, sphere=c, level="medium") for c in codes]


def _career(slug: str = "swe", *, tier: str = "strong", why: str = "Совпадает с твоими ответами") -> StudentCareer:
    return StudentCareer(
        slug=slug, name="Направление", rank=1, tier=tier, why=why,
        matched_strengths=[], try_now="Попробуй маленький проект",
    )


_MI_CODES = ["verbal", "logical", "musical", "visual", "bodily", "interpersonal", "intrapersonal", "naturalistic"]
_RIASEC_CODES = ["R", "I", "A", "S", "E", "C"]


def _junior_fixture(**overrides) -> MiResultResponse:
    """schema fixture — junior (MI)."""
    kwargs = dict(
        assessment_id=uuid.uuid4(),
        summary="Тебе нравится решать логические задачки.",
        strength_cards=[_strength_card()],
        interest_map=_interest_items(_MI_CODES),
        thinking_style_notes=[_thinking_note()],
        motivation_highlights=["Тебе важно разбираться в интересном"],
        careers=[],
        exploration_activities=["Собери конструктор LEGO"],
        is_flat_profile=False,
        created_at=_NOW,
    )
    kwargs.update(overrides)
    return MiResultResponse(**kwargs)


def _middle_fixture(**overrides) -> RiasecResultResponse:
    """schema fixture — middle (RIASEC, no flat-profile constraint exercised)."""
    kwargs = dict(
        assessment_id=uuid.uuid4(),
        summary="У тебя выражен исследовательский и артистичный тип.",
        strength_cards=[_strength_card()],
        interest_map=_interest_items(_RIASEC_CODES),
        thinking_style_notes=[_thinking_note()],
        motivation_highlights=["Тебе важно докапываться до сути"],
        careers=[_career("swe"), _career("designer", tier="good")],
        is_flat_profile=False,
        created_at=_NOW,
    )
    kwargs.update(overrides)
    return RiasecResultResponse(**kwargs)


def _senior_fixture(**overrides) -> RiasecResultResponse:
    """schema fixture — senior (RIASEC, flat profile → exactly 3 worth_trying)."""
    kwargs = dict(
        assessment_id=uuid.uuid4(),
        summary="У тебя ровный профиль без явного перевеса одной сферы.",
        strength_cards=[_strength_card()],
        interest_map=_interest_items(_RIASEC_CODES),
        thinking_style_notes=[_thinking_note()],
        motivation_highlights=["Тебе важно пробовать разное"],
        careers=[_career(f"d{i}", tier="worth_trying") for i in range(3)],
        is_flat_profile=True,
        created_at=_NOW,
    )
    kwargs.update(overrides)
    return RiasecResultResponse(**kwargs)


def test_junior_fixture_is_valid():
    response = _junior_fixture()
    assert response.interest_instrument == "mi"
    assert len(response.interest_map) == 8


def test_middle_fixture_is_valid():
    response = _middle_fixture()
    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6


def test_senior_flat_profile_fixture_is_valid():
    response = _senior_fixture()
    assert response.is_flat_profile is True
    assert len(response.careers) == 3


def test_disclaimer_defaults_to_the_fixed_server_text():
    response = _junior_fixture()
    assert response.disclaimer == DISCLAIMER
    assert response.disclaimer  # never blank


def test_extra_raw_field_is_rejected():
    with pytest.raises(ValidationError):
        _junior_fixture(match_score=42)


def test_mi_with_a_nonempty_careers_list_is_impossible():
    with pytest.raises(ValidationError):
        _junior_fixture(careers=[_career()])


def test_mi_interest_map_must_have_exactly_eight_items():
    with pytest.raises(ValidationError):
        _junior_fixture(interest_map=_interest_items(_MI_CODES[:7]))


def test_mi_exploration_activities_cannot_be_empty():
    with pytest.raises(ValidationError):
        _junior_fixture(exploration_activities=[])


def test_riasec_interest_map_must_have_exactly_six_items():
    with pytest.raises(ValidationError):
        _middle_fixture(interest_map=_interest_items(_RIASEC_CODES[:5]))


def test_riasec_careers_cannot_exceed_five():
    with pytest.raises(ValidationError):
        _middle_fixture(careers=[_career(f"d{i}") for i in range(6)])


def test_riasec_exploration_activities_must_be_empty():
    with pytest.raises(ValidationError):
        _middle_fixture(exploration_activities=["не должно тут быть"])


def test_riasec_career_why_cannot_be_empty():
    with pytest.raises(ValidationError):
        _career(why="")


def test_riasec_career_try_now_cannot_be_empty():
    with pytest.raises(ValidationError):
        StudentCareer(slug="x", name="Y", rank=1, tier="strong", why="ok", try_now="")


def test_flat_profile_wrong_career_count_is_rejected():
    with pytest.raises(ValidationError):
        _senior_fixture(careers=[_career(f"d{i}", tier="worth_trying") for i in range(2)])


def test_flat_profile_wrong_tier_is_rejected():
    with pytest.raises(ValidationError):
        _senior_fixture(careers=[
            _career("d0", tier="worth_trying"),
            _career("d1", tier="worth_trying"),
            _career("d2", tier="strong"),  # flat profile must never rank one career above another
        ])


def test_non_flat_profile_is_not_bound_by_the_three_careers_rule():
    response = _middle_fixture(is_flat_profile=False, careers=[_career(f"d{i}") for i in range(5)])
    assert len(response.careers) == 5


def test_adapter_picks_the_mi_branch_from_a_plain_dict():
    data = _junior_fixture().model_dump(mode="json")
    parsed = ResultV2Adapter.validate_python(data)
    assert isinstance(parsed, MiResultResponse)


def test_adapter_picks_the_riasec_branch_from_a_plain_dict():
    data = _middle_fixture().model_dump(mode="json")
    parsed = ResultV2Adapter.validate_python(data)
    assert isinstance(parsed, RiasecResultResponse)


def test_adapter_rejects_an_unknown_interest_instrument():
    data = _junior_fixture().model_dump(mode="json")
    data["interest_instrument"] = "holland-lite"
    with pytest.raises(ValidationError):
        ResultV2Adapter.validate_python(data)


def test_no_admin_only_raw_field_names_leak_into_the_student_schema():
    admin_fields = set(AdminAnalysisResultResponse.model_fields)
    admin_only = {
        "profile", "code", "meta", "big_five", "personality_profile",
        "personality_notes", "motivation", "motivation_top",
        "strengths", "weaknesses", "development_plan",
    }
    assert admin_only <= admin_fields  # sanity: not a typo'd set

    student_fields = set(MiResultResponse.model_fields) | set(RiasecResultResponse.model_fields)
    assert student_fields & admin_only == set()
