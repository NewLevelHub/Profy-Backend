"""Pure-function tests for report_v2_assembler.py — the DB-backed half of
the v2 response (interest_map/careers/is_flat_profile/exploration_activities)
that report_narrative_*'s pipeline deliberately doesn't touch. No DB, no
LLM: everything here is plain dicts/dataclasses in, ResultResponseV2 pieces
out."""

import uuid
from datetime import datetime, timezone

from app.models.profile import AgeGroup
from app.schemas.report_narrative import (
    MotivationNarrative,
    NarrativeCard,
    ReportNarrativeOutput,
)
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services import report_v2_assembler
from app.services.mi_service import MI_ORDER
from app.services.riasec_content import NEUTRAL_CAREER_WHY_VARIANTS
from app.services.riasec_service import HOLLAND_ORDER

_NOW = datetime.now(timezone.utc)
_DEFAULT_PERSONALITY_PROFILE = {
    "openness": 50.0, "conscientiousness": 50.0, "extraversion": 50.0,
    "agreeableness": 50.0, "emotional_stability": 50.0,
}


def _context(*, age_group: str, evidence: list[EvidenceItem]) -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=age_group,
        interest_instrument="mi" if age_group == "junior" else "riasec",
        evidence=evidence,
    )


def _narrative(strength_cards: int = 2, thinking_style_notes: int = 1) -> ReportNarrativeOutput:
    return ReportNarrativeOutput(
        summary="Тестовое резюме.",
        strength_cards=[
            NarrativeCard(title=f"Сильная сторона {i}", description="Описание") for i in range(strength_cards)
        ],
        interests=[],
        thinking_style_notes=[
            NarrativeCard(title=f"Стиль {i}", description="Описание") for i in range(thinking_style_notes)
        ],
        motivation_narrative=MotivationNarrative(title="Драйв", description="Описание"),
        career_narrative=[],
        final_analysis="Тестовый итоговый анализ, связывающий разделы.",
    )


def _direction(slug: str, holland_code: str, match_score: int, first_steps: list[str] | None = None) -> dict:
    return {
        "slug": slug,
        "name": f"Направление {slug}",
        "holland_code": holland_code,
        "match_score": match_score,
        "description": "Описание направления",
        "professions": [],
        "skills_needed": ["навык"],
        "subjects_to_develop": ["предмет"],
        "first_steps": first_steps or [],
    }


def test_junior_gets_eight_mi_items_no_careers_and_activities() -> None:
    context = _context(age_group="junior", evidence=[
        EvidenceItem(source_id="mi:logical", source_type="mi_category", text="Любишь находить закономерности"),
    ])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.junior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in MI_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=30.0,
        careers=[_direction("swe", "RIA", 5)],  # must be ignored for junior regardless
        created_at=_NOW,
    )

    assert response.interest_instrument == "mi"
    assert len(response.interest_map) == 8
    assert {item.code for item in response.interest_map} == set(MI_ORDER)
    assert response.careers == []
    assert response.exploration_activities


def test_middle_senior_get_six_riasec_items_and_valid_career_explanations() -> None:
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
    ])
    careers = [_direction("swe", "RI", 5, first_steps=["Собери первый проект"]), _direction("other", "SEC", 2)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=30.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.interest_instrument == "riasec"
    assert len(response.interest_map) == 6
    assert {item.code for item in response.interest_map} == set(HOLLAND_ORDER)
    assert response.exploration_activities == []
    assert len(response.careers) == 2
    for career in response.careers:
        assert career.why  # never empty
    # The direction whose Holland code overlaps evidence gets a grounded why + try_now.
    swe = next(c for c in response.careers if c.slug == "swe")
    assert "Любишь работать руками" in swe.why
    assert swe.try_now == "Собери первый проект"
    # The one with no overlapping evidence still gets a neutral fallback, never blank.
    other = next(c for c in response.careers if c.slug == "other")
    assert other.why == NEUTRAL_CAREER_WHY_VARIANTS[0]


def test_careers_sharing_the_same_letters_in_a_different_order_get_different_why_text() -> None:
    """Found live: Архивариус/Аудитор/Бухгалтер/Директор по логистике/
    HR-менеджер all showed the exact same `why` sentence — their Holland
    codes were the same 3 letters ("CSE"/"ESC"/"SEC"/...), and the old
    _matched_strengths_for listed every matching letter in the same fixed
    (user-rank) order regardless of which direction it was for. Now the
    order is direction-specific (riasec_service.direction_letter_weight),
    so two directions built from an identical evidence set but a different
    code must not produce byte-identical why text."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:C", source_type="riasec_category", text="Умеешь наводить порядок"),
        EvidenceItem(source_id="riasec:S", source_type="riasec_category", text="Умеешь работать с людьми"),
        EvidenceItem(source_id="riasec:E", source_type="riasec_category", text="Умеешь вести за собой"),
    ])
    careers = [_direction("buhgalter", "CSE", 6), _direction("hr", "SEC", 6)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=30.0,
        careers=careers,
        created_at=_NOW,
    )

    buhgalter = next(c for c in response.careers if c.slug == "buhgalter")
    hr = next(c for c in response.careers if c.slug == "hr")
    assert buhgalter.why != hr.why
    # Same underlying facts, matches all 3 evidence items — nothing dropped.
    assert set(buhgalter.matched_strengths) == set(hr.matched_strengths)
    assert len(buhgalter.matched_strengths) == 3


def test_careers_with_identical_evidence_after_reordering_get_a_skills_needed_differentiator() -> None:
    """Found live (residual case, after the reordering fix above): two
    directions can differ ONLY in a letter that isn't part of the student's
    confirmed top-3 evidence at all — e.g. "CSI" vs "CSR" both only match
    on C/S, in the same order, since I/R aren't vetted strengths. Reordering
    can't help here (there's nothing left to reorder), so the second such
    card gets an extra clause naming its own skills_needed — a fact about
    the job, not an unvetted claim about the student."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:C", source_type="riasec_category", text="Умеешь наводить порядок"),
        EvidenceItem(source_id="riasec:S", source_type="riasec_category", text="Умеешь работать с людьми"),
    ])
    careers = [
        _direction("first", "CSI", 6),
        _direction("second", "CSR", 5),
    ]
    careers[0]["skills_needed"] = ["Внимательность"]
    careers[1]["skills_needed"] = ["Техническая грамотность"]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 40.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=30.0,
        careers=careers,
        created_at=_NOW,
    )

    first = next(c for c in response.careers if c.slug == "first")
    second = next(c for c in response.careers if c.slug == "second")
    assert set(first.matched_strengths) == set(second.matched_strengths)  # same confirmed evidence
    assert first.why != second.why
    assert "Техническая грамотность" in second.why
    assert "Техническая грамотность" not in first.why


def test_ten_careers_with_no_overlapping_evidence_get_varied_why_text() -> None:
    """Found live 2026-08-19: a flat profile put all 10 shown careers into
    the no-overlap fallback branch, and every single one showed the exact
    same byte-identical `why` sentence. NEUTRAL_CAREER_WHY_VARIANTS must be
    cycled through (and, once exhausted, differentiated by skills_needed)
    so 10 unrelated careers never read as copy-pasted."""
    context = _context(age_group="senior", evidence=[])
    careers = []
    for i in range(10):
        d = _direction(f"d{i}", "RIA", 10 - i)
        d["skills_needed"] = [f"Навык {i}"]
        careers.append(d)
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=5.0,
        careers=careers,
        created_at=_NOW,
    )

    whys = [c.why for c in response.careers]
    assert len(whys) == 10
    assert len(set(whys)) == 10  # no two of the ten cards read identical
    for why in whys:
        assert why  # never empty


def test_flat_profile_still_gets_the_full_ranked_career_list() -> None:
    # Product decision, 2026-08-17: is_flat_profile no longer shortens or
    # flattens the tiers of the career list — that's the same top-10, ranked
    # strong/good/worth_trying by rank, as a non-flat profile gets.
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},  # flat: no spread at all
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=5.0,  # below the flat threshold
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    tiers = [c.tier for c in response.careers]
    assert tiers == ["strong", "good", "good", "worth_trying", "worth_trying"]


def test_flat_profile_with_artifact_evidence_gets_an_honest_summary_note() -> None:
    """career_match_score only ever looks at the RIASEC top-3 code — on a
    flat profile that top-3 is close to noise, and it never sees
    subject/artifact evidence at all. Found live: a student with clear
    self-reported programming/robotics interest got three clerical
    directions with zero connection to it. The scoped mitigation is telling
    the reader honestly, not silently presenting a noisy top-3 as fact."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=5.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    assert "увлечения" in response.summary


def test_flat_profile_without_artifact_evidence_gets_no_note() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=5.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.summary == _narrative().summary


def test_non_flat_profile_with_artifact_evidence_gets_no_note() -> None:
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 90.0, "I": 10.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 10.0},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=80.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is False
    assert response.summary == _narrative().summary


def test_junior_never_gets_the_flat_profile_artifact_note() -> None:
    """MiResultResponse has no careers at all — the note references
    "направления... в списке ниже", which doesn't exist for junior."""
    context = _context(age_group="junior", evidence=[
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Программирование"),
    ])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.junior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 50.0 for k in MI_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=5.0,
        careers=[],
        created_at=_NOW,
    )

    assert response.is_flat_profile is True
    assert response.summary == _narrative().summary


def test_non_flat_profile_tiers_are_strong_good_worth_trying_by_rank() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 90.0, "I": 10.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 10.0},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=80.0,  # well above the flat threshold
        careers=careers,
        created_at=_NOW,
    )

    assert response.is_flat_profile is False
    tiers = [c.tier for c in response.careers]
    assert tiers == ["strong", "good", "good", "worth_trying", "worth_trying"]


def test_same_context_gives_identical_fallback_output() -> None:
    """Determinism: no randomness, no unordered-dict dependence anywhere —
    calling twice with the same inputs must produce byte-identical output."""
    context = _context(age_group="senior", evidence=[
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Любишь работать руками"),
        EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Любишь докапываться до сути"),
    ])
    careers = [_direction("swe", "RI", 5), _direction("bio", "IS", 3)]
    profile_scores = {"R": 80.0, "I": 75.0, "A": 20.0, "S": 30.0, "E": 40.0, "C": 10.0}
    narrative = _narrative()
    assessment_id = uuid.uuid4()

    kwargs = dict(
        assessment_id=assessment_id, age_group=AgeGroup.senior, context=context, narrative=narrative,
        profile_scores=profile_scores, differentiation=45.0, careers=careers, created_at=_NOW,
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
    )
    first = report_v2_assembler.assemble_result_v2(**kwargs)
    second = report_v2_assembler.assemble_result_v2(**kwargs)

    assert first.model_dump() == second.model_dump()


def test_interest_map_levels_follow_documented_thresholds() -> None:
    context = _context(age_group="senior", evidence=[])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 75.0, "I": 55.0, "A": 20.0, "S": 0.0, "E": 50.0, "C": 100.0},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=100.0,
        careers=[],
        created_at=_NOW,
    )

    levels = {item.code: item.level for item in response.interest_map}
    assert levels["R"] == "high"    # >= 70
    assert levels["I"] == "medium"  # >= 50, < 70
    assert levels["A"] == "low"     # < 50
    assert levels["S"] == "low"
    assert levels["E"] == "medium"  # exactly 50
    assert levels["C"] == "high"


def test_interest_map_note_names_the_high_spheres() -> None:
    context = _context(age_group="senior", evidence=[])
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={"R": 75.0, "I": 55.0, "A": 20.0, "S": 0.0, "E": 50.0, "C": 100.0},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=100.0,
        careers=[],
        created_at=_NOW,
    )

    assert "Реалистичный" in response.interest_map_note
    assert "Конвенциональный" in response.interest_map_note
    assert "Артистичный" not in response.interest_map_note  # low, not high


def test_interest_map_note_handles_a_flat_profile_with_no_high_or_medium() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores={k: 20.0 for k in HOLLAND_ORDER},
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=0.0,
        careers=careers,
        created_at=_NOW,
    )

    assert response.interest_map_note  # never empty, even with nothing "high" or "medium"


def test_interest_map_note_names_a_minority_of_medium_spheres() -> None:
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    scores = {k: 30.0 for k in HOLLAND_ORDER}
    scores["R"] = 55.0
    scores["I"] = 55.0
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores=scores,
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=25.0,
        careers=careers,
        created_at=_NOW,
    )

    assert "Реалистичный" in response.interest_map_note
    assert "Исследовательский" in response.interest_map_note


def test_interest_map_note_does_not_list_a_majority_of_medium_spheres() -> None:
    """Found live: 5 of 6 RIASEC spheres landing "medium" produced a note
    naming almost the whole list as "заметнее всего" — self-contradictory
    with "без резких пиков" in the same sentence. Naming a majority isn't a
    highlight, so this must fall through to the honest flat-profile message
    instead of listing them."""
    context = _context(age_group="senior", evidence=[])
    careers = [_direction(f"d{i}", "RIA", 5 - i) for i in range(5)]
    scores = {k: 55.0 for k in HOLLAND_ORDER}
    scores["S"] = 30.0
    response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(),
        age_group=AgeGroup.senior,
        context=context,
        narrative=_narrative(),
        profile_scores=scores,
        personality_profile=_DEFAULT_PERSONALITY_PROFILE,
        differentiation=25.0,
        careers=careers,
        created_at=_NOW,
    )

    assert "Реалистичный" not in response.interest_map_note
    assert "Заметнее всего" not in response.interest_map_note
    assert response.interest_map_note


def test_build_personality_notes_covers_all_five_traits_in_a_fixed_order() -> None:
    from app.services.bigfive_content import PERSONALITY_LABELS

    notes = report_v2_assembler.build_personality_notes(False, _DEFAULT_PERSONALITY_PROFILE)

    assert [n.trait for n in notes] == list(PERSONALITY_LABELS)
    assert all(n.label and n.description for n in notes)


def test_build_personality_notes_uses_junior_wording_for_junior() -> None:
    from app.services.bigfive_content import _NOTES, _NOTES_JUNIOR

    profile = {**_DEFAULT_PERSONALITY_PROFILE, "openness": 90.0}
    junior_notes = {n.trait: n.description for n in report_v2_assembler.build_personality_notes(True, profile)}
    adult_notes = {n.trait: n.description for n in report_v2_assembler.build_personality_notes(False, profile)}

    assert junior_notes["openness"] == _NOTES_JUNIOR["openness"]["high"]
    assert adult_notes["openness"] == _NOTES["openness"]["high"]
    assert junior_notes["openness"] != adult_notes["openness"]


def test_build_personality_note_names_a_minority_of_high_traits() -> None:
    profile = {**_DEFAULT_PERSONALITY_PROFILE, "openness": 75.0}

    note = report_v2_assembler.build_personality_note(profile)

    assert "Открытость новому" in note
    assert "Организованность" not in note


def test_build_personality_note_falls_back_when_nothing_stands_out() -> None:
    note = report_v2_assembler.build_personality_note(_DEFAULT_PERSONALITY_PROFILE)

    assert "Ярко выражено" not in note
    assert note


def test_build_personality_note_falls_back_when_a_majority_of_traits_are_high() -> None:
    """Same guard as build_interest_map_note: naming traits only reads as a
    highlight if it's not most of them."""
    profile = {trait: 75.0 for trait in _DEFAULT_PERSONALITY_PROFILE}

    note = report_v2_assembler.build_personality_note(profile)

    assert "Ярко выражено" not in note


def test_build_personality_note_names_a_minority_of_low_growth_eligible_traits() -> None:
    """A student who is honestly weak on a couple of skill-like traits
    (everything else mid) must be told so, not falsely called "balanced" —
    the whole point of this feature."""
    profile = {**_DEFAULT_PERSONALITY_PROFILE, "openness": 0.0, "conscientiousness": 0.0}

    note = report_v2_assembler.build_personality_note(profile)

    assert "Ярко выражено" not in note
    assert "над чем интересно поработать" in note
    assert "Открытость новому" in note
    assert "Организованность" in note


def test_build_personality_note_never_names_extraversion_or_agreeableness_as_low() -> None:
    """Introversion/directness are temperament, not a deficiency to "work
    on" — low E/A must never appear in the growth callout, even when they
    genuinely cross the low band and nothing else does (which would
    otherwise fall back to the honest "balanced" message instead of
    inventing something to say)."""
    profile = {**_DEFAULT_PERSONALITY_PROFILE, "extraversion": 0.0, "agreeableness": 0.0}

    note = report_v2_assembler.build_personality_note(profile)

    assert "над чем интересно поработать" not in note
    assert "Общительность" not in note
    assert "Доброжелательность" not in note


def test_build_personality_note_reports_both_high_and_low_traits_together() -> None:
    profile = {**_DEFAULT_PERSONALITY_PROFILE, "openness": 90.0, "conscientiousness": 5.0}

    note = report_v2_assembler.build_personality_note(profile)

    assert "Ярко выражено: Открытость новому" in note
    assert "над чем интересно поработать: Организованность" in note


def test_build_personality_note_falls_back_when_all_growth_eligible_traits_are_low() -> None:
    profile = {
        **_DEFAULT_PERSONALITY_PROFILE,
        "openness": 10.0, "conscientiousness": 10.0, "emotional_stability": 10.0,
    }

    note = report_v2_assembler.build_personality_note(profile)

    assert "над чем интересно поработать" not in note


def test_assemble_result_v2_includes_personality_notes_for_junior_and_senior() -> None:
    junior_context = _context(age_group="junior", evidence=[])
    junior_response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(), age_group=AgeGroup.junior, context=junior_context,
        narrative=_narrative(), profile_scores={k: 40.0 for k in MI_ORDER},
        personality_profile={**_DEFAULT_PERSONALITY_PROFILE, "openness": 80.0},
        differentiation=30.0, careers=[], created_at=_NOW,
    )
    senior_context = _context(age_group="senior", evidence=[])
    senior_response = report_v2_assembler.assemble_result_v2(
        assessment_id=uuid.uuid4(), age_group=AgeGroup.senior, context=senior_context,
        narrative=_narrative(), profile_scores={k: 40.0 for k in HOLLAND_ORDER},
        personality_profile={**_DEFAULT_PERSONALITY_PROFILE, "openness": 80.0},
        differentiation=30.0, careers=[], created_at=_NOW,
    )

    assert len(junior_response.personality_notes) == 5
    assert len(senior_response.personality_notes) == 5
    junior_openness = next(n for n in junior_response.personality_notes if n.trait == "openness").description
    senior_openness = next(n for n in senior_response.personality_notes if n.trait == "openness").description
    assert junior_openness != senior_openness  # junior wording differs from adult wording
    # Guards the wiring itself, not just build_personality_note() in isolation
    # — personality_note has a schema default, so a dropped kwarg in
    # assemble_result_v2() would silently fall back instead of failing loudly.
    assert "Открытость новому" in junior_response.personality_note
    assert "Открытость новому" in senior_response.personality_note
