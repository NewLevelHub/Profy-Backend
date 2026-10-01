"""No DB involved for hybrid_profile — pure-function tie logic, the
cheapest layer to verify (mirrors test_riasec_service.py's convention)."""
from app.services import professional_types_service


def test_hybrid_profile_flags_a_tie() -> None:
    scores = {"practical": 8, "technical": 8, "social": 3, "sign": 2, "artistic": 1}
    assert professional_types_service.hybrid_profile(scores) == ["practical", "technical"]


def test_hybrid_profile_flags_one_point_apart() -> None:
    scores = {"practical": 8, "technical": 7, "social": 3, "sign": 2, "artistic": 1}
    assert professional_types_service.hybrid_profile(scores) == ["practical", "technical"]


def test_hybrid_profile_none_when_clear_leader() -> None:
    scores = {"practical": 8, "technical": 5, "social": 3, "sign": 2, "artistic": 1}
    assert professional_types_service.hybrid_profile(scores) is None


def test_hybrid_profile_none_when_no_scores() -> None:
    assert professional_types_service.hybrid_profile(None) is None
    assert professional_types_service.hybrid_profile({}) is None


def test_hybrid_profile_tie_break_uses_fixed_scale_order() -> None:
    # artistic and practical tie for the top two at 5 each — SCALE_ORDER
    # puts practical before artistic, so it must win the "top" slot
    # deterministically regardless of dict iteration order.
    scores = {"artistic": 5, "practical": 5, "technical": 1, "social": 1, "sign": 1}
    assert professional_types_service.hybrid_profile(scores) == ["practical", "artistic"]
