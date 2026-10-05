"""«Сильные стороны» selection (PRO-432): which instrument results may become a
student-facing strength card, how they are grounded, and how a completed
RIASEC profile fills the section with five non-duplicated observations. Pure — no DB."""
import pytest

from app.i18n import use_locale
from app.schemas.report_narrative import NarrativeCard
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.schemas.student_strengths import OnboardingArtifact, StrengthInputs
from app.services import student_strengths_service as svc
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate
from tests.strength_fixtures import astur_snapshot, belbin_totals, rich_inputs


def _ids(inputs: StrengthInputs) -> list[str]:
    with use_locale("ru"):
        return [c.source_id for c in svc.select_strengths(inputs)]


def _select(inputs: StrengthInputs, locale: str = "ru"):
    with use_locale(locale):
        return svc.select_strengths(inputs)


# ── АСТУР ────────────────────────────────────────────────────────────────────


def test_astur_best_task_groups_become_task_result_cards():
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 90, "geometric_figures": 80, "analogies": 65}))

    cards = _select(inputs)

    assert [c.source_id for c in cards] == ["strength:astur:numeric", "strength:astur:spatial"]
    assert {c.basis for c in cards} == {"task_result"}


def test_astur_group_below_threshold_is_not_a_strength():
    assert _ids(StrengthInputs(astur=astur_snapshot({"numeric_series": 55}))) == []


def test_astur_problem_protocol_gives_no_confident_card():
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 95}, ok=False))
    assert _ids(inputs) == []


def test_astur_quick_instructions_need_their_own_accuracy():
    assert _ids(StrengthInputs(astur=astur_snapshot(quick_correct=(10, 12)))) == ["strength:astur:instructions"]
    assert _ids(StrengthInputs(astur=astur_snapshot(quick_correct=(6, 12)))) == []


def test_astur_repeat_exposure_is_kept_as_a_quality_flag():
    cards = _select(StrengthInputs(astur=astur_snapshot({"numeric_series": 90}, repeat_exposure=True)))
    assert cards[0].quality_flags == ["astur_repeat_exposure"]


def test_astur_card_carries_no_iq_label_or_number():
    card = _select(StrengthInputs(astur=astur_snapshot({"numeric_series": 90})))[0]
    text = f"{card.title} {card.description}".lower()
    assert "интеллект" not in text and "iq" not in text
    assert not any(ch.isdigit() for ch in text)


# ── ДДО ──────────────────────────────────────────────────────────────────────


def test_ddo_want_and_can_in_one_sphere_is_a_strength():
    inputs = StrengthInputs(
        ddo_interest={"practical": 0, "technical": 5, "social": 1, "sign": 1, "artistic": 1},
        ddo_abilities={"practical": 0, "technical": 2, "social": 1, "sign": 1, "artistic": 0},
    )
    cards = _select(inputs)
    assert [c.source_id for c in cards] == ["strength:ddo:technical"]
    assert "разбираться в технике" in cards[0].title
    assert "человек — техника" not in cards[0].title


def test_ddo_scales_are_normalized_separately_not_compared_raw():
    """Interest 4 of 8 picks is half — below the bar — even though the raw
    number beats the ability maximum of 3."""
    inputs = StrengthInputs(
        ddo_interest={"practical": 0, "technical": 4, "social": 0, "sign": 0, "artistic": 0},
        ddo_abilities={"practical": 0, "technical": 3, "social": 0, "sign": 0, "artistic": 0},
    )
    assert "strength:ddo:technical" not in _ids(inputs)


def test_ddo_two_leading_spheres_make_one_hybrid_card():
    inputs = StrengthInputs(
        ddo_interest={"practical": 0, "technical": 6, "social": 0, "sign": 6, "artistic": 0},
        ddo_abilities={"practical": 0, "technical": 3, "social": 0, "sign": 3, "artistic": 0},
    )
    assert _ids(inputs) == ["strength:ddo_hybrid:technical+sign"]


def test_ddo_want_more_than_can_is_an_interest_to_try_not_an_ability():
    inputs = StrengthInputs(
        ddo_interest={"practical": 0, "technical": 8, "social": 0, "sign": 0, "artistic": 0},
        ddo_abilities={"practical": 0, "technical": 1, "social": 0, "sign": 0, "artistic": 0},
    )
    cards = _select(inputs)
    assert [c.source_id for c in cards] == ["strength:ddo_interest:technical"]
    assert cards[0].basis == "interest"
    assert "интерес" in cards[0].description


def test_ddo_can_more_than_want_is_a_skill_not_a_calling():
    inputs = StrengthInputs(
        ddo_interest={"practical": 0, "technical": 1, "social": 0, "sign": 0, "artistic": 0},
        ddo_abilities={"practical": 0, "technical": 3, "social": 0, "sign": 0, "artistic": 0},
    )
    cards = _select(inputs)
    assert [c.source_id for c in cards] == ["strength:ddo_ability:technical"]
    assert "такие занятия привлекают тебя меньше" in cards[0].description
    assert "человек — техника" not in f"{cards[0].title} {cards[0].description}"


# ── Белбин ───────────────────────────────────────────────────────────────────


def test_belbin_leading_role_is_a_team_contribution_with_age_caveat():
    cards = _select(StrengthInputs(belbin_role_totals=belbin_totals(finisher=18)))
    assert [c.source_id for c in cards] == ["strength:belbin:finisher"]
    assert "а не закреплённая роль" in cards[0].description


def test_belbin_tie_is_merged_not_won_by_key_order():
    cards = _select(StrengthInputs(belbin_role_totals=belbin_totals(plant=15, finisher=15)))
    assert [c.source_id for c in cards] == ["strength:belbin:plant+finisher"]


def test_belbin_three_way_tie_is_no_clear_signal():
    totals = belbin_totals(plant=14, finisher=14, coordinator=14)
    assert _ids(StrengthInputs(belbin_role_totals=totals)) == []


def test_belbin_weak_leader_or_avoidance_role_is_never_a_strength():
    assert _ids(StrengthInputs(belbin_role_totals=belbin_totals(plant=11))) == []
    # Every role in the avoidance zone: nothing to show.
    flat_low = {role: 2 for role in belbin_totals()}
    assert _ids(StrengthInputs(belbin_role_totals=flat_low)) == []


# ── Бойко + Кондаш ───────────────────────────────────────────────────────────


def test_empathy_names_its_strongest_channel():
    channels = {"rational": 2, "emotional": 6, "intuitive": 3, "attitudes": 3, "penetration": 4, "identification": 4}
    cards = _select(StrengthInputs(empathy_channels=channels, empathy_level="average"))
    assert [c.source_id for c in cards] == ["strength:empathy:emotional"]


def test_empathy_channel_tie_gives_one_general_card_not_six():
    channels = {"rational": 5, "emotional": 5, "intuitive": 3, "attitudes": 3, "penetration": 4, "identification": 4}
    assert _ids(StrengthInputs(empathy_channels=channels, empathy_level="average")) == ["strength:empathy:general"]


def test_very_high_empathy_keeps_the_boundary_caveat():
    channels = {c: 6 for c in ("rational", "emotional", "intuitive", "attitudes", "penetration", "identification")}
    card = _select(StrengthInputs(empathy_channels=channels, empathy_level="very_high"))[0]
    assert "границы" in card.description


def test_low_empathy_and_low_confidence_are_not_strengths():
    channels = {c: 1 for c in ("rational", "emotional", "intuitive", "attitudes", "penetration", "identification")}
    inputs = StrengthInputs(empathy_channels=channels, empathy_level="very_low", confidence_level="low")
    assert _ids(inputs) == []


def test_high_social_confidence_is_a_strength():
    assert _ids(StrengthInputs(confidence_level="high")) == ["strength:social_confidence"]
    assert _ids(StrengthInputs(confidence_level="normative")) == []


# ── Элерс ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("level,expected", [
    ("moderately_high", ["strength:elers"]),
    ("medium", []),
    ("low", []),
    ("too_high", []),
])
def test_only_moderately_high_elers_is_a_strength(level, expected):
    assert _ids(StrengthInputs(elers_level=level)) == expected


# ── RIASEC ───────────────────────────────────────────────────────────────────


def test_riasec_alone_is_an_interest_to_check_not_an_ability():
    cards = _select(StrengthInputs(riasec_confirmed=["S", "E"]))
    assert [card.evidence_ids for card in cards] == [["riasec:S"], ["riasec:E"]]
    assert {card.basis for card in cards} == {"interest"}
    text = " ".join(f"{card.title} {card.description}" for card in cards).lower()
    assert "хорошо понимаешь людей" not in text and "умеешь" not in text


def test_riasec_interest_cards_have_distinct_child_friendly_wording():
    cards = _select(StrengthInputs(riasec_ranked=["R", "I", "A", "S", "E", "C"]))

    assert len(cards) == 5
    assert len({card.title for card in cards}) == 5
    assert len({card.description for card in cards}) == 5
    assert all("Тебе может быть интересно:" not in card.title for card in cards)


def test_riasec_confirmed_by_a_second_instrument_is_a_cross_signal():
    inputs = StrengthInputs(riasec_confirmed=["C"], belbin_role_totals=belbin_totals(finisher=18))
    cards = _select(inputs)
    assert [c.source_id for c in cards] == ["strength:cross:order"]
    assert cards[0].basis == "cross_signal"
    assert cards[0].evidence_ids == ["riasec:C", "belbin:finisher"]


def test_cross_signal_uses_a_supporting_belbin_role_too():
    inputs = StrengthInputs(riasec_confirmed=["E"], belbin_role_totals=belbin_totals(plant=18, coordinator=13))
    ids = _ids(inputs)
    assert "strength:cross:lead" in ids
    # plant stays its own team card; coordinator was only a confirmation.
    assert "strength:belbin:plant" in ids


# ── selection ────────────────────────────────────────────────────────────────


def test_rich_profile_caps_at_five():
    cards = _select(rich_inputs())

    assert [c.source_id for c in cards] == [
        "strength:cross:people",
        "strength:cross:research",
        "strength:astur:numeric",
        "strength:belbin:plant",
        "strength:elers",
    ]
    assert len(cards) == 5


def test_no_fact_backs_two_cards():
    cards = _select(rich_inputs())
    evidence = [e for c in cards for e in c.evidence_ids]
    assert len(evidence) == len(set(evidence))


def test_nothing_measured_means_no_cards_and_no_padding():
    assert _ids(StrengthInputs()) == []


def test_few_valid_signals_give_few_cards():
    assert len(_select(StrengthInputs(elers_level="moderately_high", riasec_confirmed=["A"]))) == 2


def test_selection_is_deterministic():
    assert _select(rich_inputs()) == _select(rich_inputs())


def test_ru_and_kk_show_the_same_cards():
    ru = _select(rich_inputs(), "ru")
    kk = _select(rich_inputs(), "kk")
    assert [(c.source_id, c.basis, c.evidence_ids) for c in ru] == [(c.source_id, c.basis, c.evidence_ids) for c in kk]
    assert [c.title for c in ru] != [c.title for c in kk]


def test_lie_scale_flag_keeps_only_task_results_and_interests():
    cards = _select(rich_inputs(lie_flagged=True))
    assert {c.basis for c in cards} <= {"task_result", "interest", "self_report"}
    assert {c.source_type for c in cards} <= {"astur", "professional_types", "riasec"}
    assert all(c.basis in {"task_result", "interest"} for c in cards)
    assert "strength:astur:numeric" in [c.source_id for c in cards]


def test_weak_overall_profile_keeps_local_task_result_and_exploratory_interest():
    """A real profile may have no broad self-report strength but still contain
    one well-performed task and one activity the student repeatedly chose."""
    inputs = StrengthInputs(
        astur=astur_snapshot(
            {"classification": 67, "generalization": 0},
            repeat_exposure=True,
        ),
        ddo_interest={"practical": 3, "technical": 6, "social": 3, "sign": 3, "artistic": 5},
        ddo_abilities={"practical": 0, "technical": 0, "social": 1, "sign": 2, "artistic": 0},
        riasec_ranked=["A", "R", "S", "I", "E", "C"],
        lie_flagged=True,
        subjects_easy=["Информатика", "История", "Английский язык"],
    )

    cards = _select(inputs)

    assert [c.source_id for c in cards] == [
        "strength:astur:categorization",
        "strength:ddo_interest:technical",
        "strength:interest:A",
        "strength:interest:S",
        "strength:interest:I",
    ]
    assert len(cards) == 5
    assert all(card.source_type != "onboarding" for card in cards)
    assert cards[0].basis == "task_result"
    assert "повторная попытка" in cards[0].description
    assert cards[1].basis == "interest"


def test_ddo_and_riasec_do_not_repeat_the_same_activity_area():
    inputs = StrengthInputs(
        riasec_ranked=["R", "A", "S", "I", "E", "C"],
        ddo_interest={"practical": 0, "technical": 8, "social": 0, "sign": 0, "artistic": 0},
        ddo_abilities={"practical": 0, "technical": 0, "social": 0, "sign": 0, "artistic": 0},
    )

    cards = _select(inputs)

    assert len(cards) == 5
    assert "strength:ddo_interest:technical" in [card.source_id for card in cards]
    assert "strength:interest:R" not in [card.source_id for card in cards]


# ── onboarding data is excluded ─────────────────────────────────────────────


def test_onboarding_data_does_not_become_a_strength_card():
    inputs = StrengthInputs(
        subjects_easy=["Математика", "Физика"],
        subjects_liked=["История"],
        artifacts=[OnboardingArtifact(id="1", value="Шахматы")],
    )
    assert _select(inputs) == []


def test_hobbies_do_not_become_strength_cards():
    inputs = StrengthInputs(artifacts=[
        OnboardingArtifact(id="1", value="Программирование"),
        OnboardingArtifact(id="2", value="Робототехника"),
        OnboardingArtifact(id="3", value="IT/программирование"),
    ])
    assert _select(inputs) == []


def test_onboarding_subjects_are_excluded_in_every_locale():
    inputs = StrengthInputs(subjects_liked=["История"])
    assert _select(inputs, "ru") == []
    assert _select(inputs, "kk") == []


# ── wording passes the narrative validator ───────────────────────────────────


@pytest.mark.parametrize("locale", ["ru", "kk"])
@pytest.mark.parametrize("inputs", [
    rich_inputs(),
    rich_inputs(empathy_level="very_high", riasec_confirmed=["A", "R"]),
    StrengthInputs(riasec_confirmed=["R", "C"], ddo_interest={"practical": 0, "technical": 1, "social": 0, "sign": 0, "artistic": 0},
                   ddo_abilities={"practical": 3, "technical": 3, "social": 0, "sign": 0, "artistic": 0}),
    StrengthInputs(belbin_role_totals=belbin_totals(shaper=15, resource_investigator=15),
                   astur=astur_snapshot({"classification": 80, "generalization": 80}, quick_correct=(12, 12))),
])
def test_every_card_wording_passes_the_validator(inputs, locale):
    with use_locale(locale):
        context = ReportNarrativeContext(strength_candidates=svc.select_strengths(inputs))
        output = build_fallback_narrative(context, locale=locale)
    assert output.strength_cards
    assert validate(output, context, language=locale) == []


# ── storage / fingerprint ────────────────────────────────────────────────────


def test_stored_cards_carry_basis_matched_by_cited_id():
    candidates = _select(rich_inputs())
    reworded = [
        NarrativeCard(title=f"T{i}", description=f"D{i}", evidence_ids=[c.source_id])
        for i, c in enumerate(reversed(candidates))
    ]

    stored = svc.stored_cards(reworded, candidates)

    assert stored[0]["title"] == "T0"
    assert stored[0]["description"] == candidates[-1].description
    assert stored[0]["basis"] == candidates[-1].basis
    assert all("try_now" not in card for card in stored)
    assert "source_id" not in stored[0] and "evidence_ids" not in stored[0]


def test_mark_fresh_records_rules_version_and_outdated_reports_are_detected():
    fresh = svc.mark_fresh({"differentiation": 12.5})

    assert fresh == {"differentiation": 12.5, "strengths_rules_version": svc.student_strengths_rules.version}
    assert svc.rules_version_is_outdated(fresh) is False
    assert svc.rules_version_is_outdated({}) is True
    assert svc.rules_version_is_outdated({"strengths_rules_version": -1}) is True
