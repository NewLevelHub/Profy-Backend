"""Goal scenario (A/B/C) resolution for display — the only part of the old
goal-overlay feature that is still read (by `admin_service`)."""
from typing import Literal, Optional

from app.i18n.catalog import tr
from app.models.assessment import AssessmentGoal
from app.models.profile import AgeGroup
from app.services import assessment_shared

_SCENARIO_BY_GOAL: dict[AssessmentGoal, Literal["A", "B", "C"]] = {
    AssessmentGoal.explore: "A",
    AssessmentGoal.profession: "B",
    AssessmentGoal.university: "C",
}


def _middle_university_downgrade_note() -> str:
    return tr("goal_overlay")["middle_university_downgrade_note"]


def _get_effective_goal_and_scenario(
    age_group: AgeGroup, primary_goal: AssessmentGoal
) -> tuple[AssessmentGoal, Literal["A", "B", "C"], bool, Optional[str]]:
    """Display-layer wrapper around `assessment_shared.get_effective_goal` — the
    scenario letter and "redirected" banner text shown here must always agree
    with what report generation actually runs under, so the goal
    mapping itself lives in that one shared function, not here."""
    effective_goal = assessment_shared.get_effective_goal(age_group, primary_goal)
    scenario = _SCENARIO_BY_GOAL[effective_goal]

    if age_group == AgeGroup.junior:
        redirected = primary_goal != AssessmentGoal.explore
        return effective_goal, scenario, redirected, None

    if age_group == AgeGroup.middle and primary_goal == AssessmentGoal.university:
        return effective_goal, scenario, True, _middle_university_downgrade_note()

    return effective_goal, scenario, False, None
