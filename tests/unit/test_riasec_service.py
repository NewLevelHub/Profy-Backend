"""No DB/Redis involved — pure-function scoring math, the cheapest layer to
verify. Also serves as the infra smoke test for anything that doesn't need
`db_session`/`client` (no event loop surprises, no fixtures required)."""

from app.services import riasec_service


def test_normalize_scales_to_percent_of_maximum() -> None:
    raw = {"R": 10, "I": 0, "A": 15, "S": 0, "E": 0, "C": 0}
    counts = {"R": 4, "I": 4, "A": 3, "S": 4, "E": 4, "C": 4}

    normalized = riasec_service.normalize(raw, counts)

    # R: 10 / (4*5) * 100 = 50.0 ; A: 15 / (3*5) * 100 = 100.0 (answered max every time)
    assert normalized["R"] == 50.0
    assert normalized["A"] == 100.0
    assert normalized["I"] == 0.0


def test_normalize_treats_zero_questions_as_zero_not_division_error() -> None:
    normalized = riasec_service.normalize({}, {"R": 0, "I": 4, "A": 4, "S": 4, "E": 4, "C": 4})
    assert normalized["R"] == 0.0


def test_top_code_breaks_ties_by_fixed_holland_order() -> None:
    # R and I tie at 80.0 — HOLLAND_ORDER = ["R", "I", "A", "S", "E", "C"],
    # so R must win the tie deterministically, not depend on dict iteration.
    normalized = {"R": 80.0, "I": 80.0, "A": 50.0, "S": 20.0, "E": 10.0, "C": 5.0}
    assert riasec_service.top_code(normalized, limit=2) == ["R", "I"]


def test_differentiation_is_spread_between_max_and_min() -> None:
    normalized = {"R": 90.0, "I": 60.0, "A": 40.0, "S": 30.0, "E": 20.0, "C": 10.0}
    assert riasec_service.differentiation(normalized) == 80.0


def test_consistency_high_for_adjacent_types_on_the_hexagon() -> None:
    # R and I are adjacent on the RIASEC hexagon (distance 1) -> "high"
    assert riasec_service.consistency(["R", "I"]) == "high"


def test_consistency_low_for_opposite_types_on_the_hexagon() -> None:
    # R and S sit opposite each other (distance 3) -> "low"
    assert riasec_service.consistency(["R", "S"]) == "low"
