from app.models.profile import AgeGroup
from app.models.assessment import AssessmentGoal
from app.services.goal_overlay_service import _get_effective_goal_and_scenario, _get_secondary_goals


def test_junior_always_redirects_to_explore_scenario_a() -> None:
    # explore
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.junior, AssessmentGoal.explore)
    assert eff == AssessmentGoal.explore
    assert scen == "A"
    assert redir is False
    assert note is None

    # profession
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.junior, AssessmentGoal.profession)
    assert eff == AssessmentGoal.explore
    assert scen == "A"
    assert redir is True
    assert note is None

    # university
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.junior, AssessmentGoal.university)
    assert eff == AssessmentGoal.explore
    assert scen == "A"
    assert redir is True
    assert note is None


def test_middle_redirects_university_to_profession_scenario_b() -> None:
    # explore
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.middle, AssessmentGoal.explore)
    assert eff == AssessmentGoal.explore
    assert scen == "A"
    assert redir is False
    assert note is None

    # profession
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.middle, AssessmentGoal.profession)
    assert eff == AssessmentGoal.profession
    assert scen == "B"
    assert redir is False
    assert note is None

    # university -> redirects/downgrades
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.middle, AssessmentGoal.university)
    assert eff == AssessmentGoal.profession
    assert scen == "B"
    assert redir is True
    assert "поступление в вуз еще впереди" in note


def test_senior_gets_all_scenarios_directly() -> None:
    # explore
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.senior, AssessmentGoal.explore)
    assert eff == AssessmentGoal.explore
    assert scen == "A"
    assert redir is False
    assert note is None

    # profession
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.senior, AssessmentGoal.profession)
    assert eff == AssessmentGoal.profession
    assert scen == "B"
    assert redir is False
    assert note is None

    # university
    eff, scen, redir, note = _get_effective_goal_and_scenario(AgeGroup.senior, AssessmentGoal.university)
    assert eff == AssessmentGoal.university
    assert scen == "C"
    assert redir is False
    assert note is None


def test_secondary_goals_selection() -> None:
    # junior
    assert _get_secondary_goals(AgeGroup.junior, AssessmentGoal.explore) == []

    # middle
    assert _get_secondary_goals(AgeGroup.middle, AssessmentGoal.explore) == [AssessmentGoal.profession]
    assert _get_secondary_goals(AgeGroup.middle, AssessmentGoal.profession) == [AssessmentGoal.explore]

    # senior
    sec_for_explore = _get_secondary_goals(AgeGroup.senior, AssessmentGoal.explore)
    assert AssessmentGoal.profession in sec_for_explore
    assert AssessmentGoal.university in sec_for_explore
    assert len(sec_for_explore) == 2
