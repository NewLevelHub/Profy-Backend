"""PRO-338 Ф2.5 — interpret_role_totals: dominant role = max score; 2nd/3rd
rank = supporting; roles scoring <=avoidance_max_score = avoidance zone.
Composite/multi-employee team analysis is explicitly out of MVP scope
(spec's own п.18) — nothing here accepts more than one role_totals dict."""
from app.config import BelbinThresholds
from app.services.belbin_service import interpret_role_totals

_ALL_8_ROLES = [
    "implementer", "coordinator", "shaper", "plant",
    "resource_investigator", "evaluator", "team_worker", "finisher",
]


def _role_totals(**overrides: int) -> dict[str, int]:
    base = dict.fromkeys(_ALL_8_ROLES, 5)
    base.update(overrides)
    return base


def test_dominant_role_is_the_max_scorer() -> None:
    totals = _role_totals(coordinator=20)
    result = interpret_role_totals(totals)
    assert result.dominant_role == "coordinator"
    assert result.ranked_roles[0] == "coordinator"


def test_supporting_roles_are_rank_2_and_3() -> None:
    totals = _role_totals(coordinator=20, shaper=15, plant=12)
    result = interpret_role_totals(totals)
    assert result.dominant_role == "coordinator"
    assert result.supporting_roles == ["shaper", "plant"]


def test_avoidance_zone_uses_configured_threshold_not_rank() -> None:
    totals = _role_totals(coordinator=20, shaper=3, implementer=2)
    thresholds = BelbinThresholds(version=1, avoidance_max_score=3)
    result = interpret_role_totals(totals, thresholds=thresholds)
    assert set(result.avoidance_roles) == {"shaper", "implementer"}
    # Avoidance is independent of rank — none of the avoidance roles here
    # happen to be 2nd/3rd place, but that's incidental to this fixture,
    # not a rule the function enforces.
    assert "coordinator" not in result.avoidance_roles


def test_no_avoidance_roles_when_everyone_scores_above_threshold() -> None:
    totals = _role_totals(coordinator=20)  # everyone else stays at 5, > 3
    result = interpret_role_totals(totals)
    assert result.avoidance_roles == []


def test_ties_break_deterministically_by_canonical_role_order() -> None:
    # implementer sorts before coordinator in ROLES' own key order, and both
    # tie at the max score here.
    totals = _role_totals(implementer=15, coordinator=15)
    result = interpret_role_totals(totals)
    assert result.dominant_role == "implementer"
    assert result.ranked_roles[1] == "coordinator"


def test_ranked_roles_covers_all_8_exactly_once() -> None:
    totals = _role_totals(coordinator=20, shaper=3)
    result = interpret_role_totals(totals)
    assert sorted(result.ranked_roles) == sorted(_ALL_8_ROLES)
    assert len(result.ranked_roles) == 8
