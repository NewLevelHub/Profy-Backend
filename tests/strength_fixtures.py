"""Shared inputs for the «Сильные стороны» selection tests (PRO-432)."""
from datetime import datetime, timezone

from app.schemas.astur import (
    AsturResultSnapshot,
    ProtocolFlag,
    ProtocolQuality,
    QuickInstructionsResult,
    SubjectProfileResult,
    SubtestResult,
)
from app.schemas.student_strengths import OnboardingArtifact, StrengthInputs

_ASTUR_SUBTESTS = (
    "awareness", "analogies", "classification", "generalization",
    "logical_schemas", "numeric_series", "geometric_figures",
)


def astur_snapshot(
    percents: dict[str, float] | None = None,
    *,
    ok: bool = True,
    quick_correct: tuple[int, int] | None = None,
    repeat_exposure: bool = False,
) -> AsturResultSnapshot:
    """Every subtest scored out of 10; `percents` overrides the default 40%.
    `quick_correct` = (correct, total) on the timed commands."""
    percents = percents or {}
    subtests = [
        SubtestResult(
            key=key, score=percents.get(key, 40) / 10, max_score=10, percent=percents.get(key, 40),
            item_count=10, answered=10, in_overall=True,
        )
        for key in _ASTUR_SUBTESTS
    ]
    quick = None
    if quick_correct is not None:
        correct, total = quick_correct
        quick = QuickInstructionsResult(
            status="ok", total=total, on_time=total,
            first_half_correct=correct // 2, first_half_total=total // 2,
            second_half_correct=correct - correct // 2, second_half_total=total - total // 2,
        )
    flags = [] if ok else [ProtocolFlag(code="many_blank_answers", subtest="analogies", count=5)]
    return AsturResultSnapshot(
        scoring_version="3",
        bank_version=1,
        completed_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        history={"attempt_number": 2 if repeat_exposure else 1, "repeat_exposure": repeat_exposure},
        subtests=subtests,
        overall_percent=40,
        subject_profile=SubjectProfileResult(status="insufficient_data", areas=[]),
        quick_instructions=quick,
        protocol_quality=ProtocolQuality(ok=ok, flags=flags),
    )


def belbin_totals(**overrides: int) -> dict[str, int]:
    """70 points spread over 8 roles, every role above the avoidance zone."""
    totals = {
        "implementer": 8, "coordinator": 8, "shaper": 8, "plant": 8,
        "resource_investigator": 8, "evaluator": 8, "team_worker": 8, "finisher": 8,
    }
    totals.update(overrides)
    return totals


def rich_inputs(**overrides) -> StrengthInputs:
    """A student with a signal in every instrument."""
    data = dict(
        riasec_confirmed=["I", "S"],
        riasec_ranked=["I", "S", "R", "A", "E", "C"],
        ddo_interest={"practical": 1, "technical": 6, "social": 3, "sign": 2, "artistic": 1},
        ddo_abilities={"practical": 1, "technical": 3, "social": 2, "sign": 1, "artistic": 0},
        belbin_role_totals=belbin_totals(plant=16, evaluator=9, team_worker=5, finisher=4),
        astur=astur_snapshot({"numeric_series": 90, "analogies": 70, "logical_schemas": 70}),
        empathy_channels={
            "rational": 3, "emotional": 6, "intuitive": 3, "attitudes": 3, "penetration": 4, "identification": 4,
        },
        empathy_level="average",
        confidence_level="high",
        elers_level="moderately_high",
        subjects_easy=["Математика"],
        artifacts=[OnboardingArtifact(id="art-1", value="Робототехника")],
    )
    data.update(overrides)
    return StrengthInputs(**data)
