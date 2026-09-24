"""PRO-338 Ф1.1 — content integrity for professional_types_bank.py. No DB
involved (pure data checks), mirrors test_riasec_service.py's "cheapest
layer to verify" convention."""
from scripts.professional_types_bank import PAIRS, QUESTIONS

_SCALES = {"practical", "technical", "social", "sign", "artistic"}


def test_pairs_has_exactly_20_entries_covering_all_five_scales_on_both_sides() -> None:
    assert len(PAIRS) == 20
    scales_used = {opt["scale"] for p in PAIRS for opt in (p["option_a"], p["option_b"])}
    assert scales_used == _SCALES


def test_pair_options_use_unique_question_orders() -> None:
    orders = [opt["order"] for p in PAIRS for opt in (p["option_a"], p["option_b"])]
    assert len(orders) == len(set(orders)) == 40


def test_abilities_questions_cover_all_five_scales_exactly_once() -> None:
    assert len(QUESTIONS) == 5
    assert {q["scale"] for q in QUESTIONS} == _SCALES
    orders = [q["order"] for q in QUESTIONS]
    assert len(orders) == len(set(orders)) == 5
