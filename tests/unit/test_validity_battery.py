"""PRO-298: interleave_validity places the protocol-validity items inside the
Big Five block deterministically — spread out, never on the edges, no runs,
same battery every time for a given assessment id, nothing dropped."""
import uuid

from app.models.question import Question, QuestionInstrument, ValidityRole
from app.services.validity_battery import (
    _EDGE_MARGIN,
    _MIN_BASE_BETWEEN,
    interleave_validity,
)


def _base(n: int) -> list[Question]:
    return [
        Question(
            instrument=QuestionInstrument.big_five, text=f"bf{i}", order=100 + i
        )
        for i in range(n)
    ]


def _validity(n: int) -> list[Question]:
    return [
        Question(
            instrument=QuestionInstrument.validity,
            validity_role=ValidityRole.sd_key,
            text=f"v{i}",
            order=1000 + i,
        )
        for i in range(n)
    ]


def _positions(seq: list[Question]) -> list[int]:
    return [i for i, q in enumerate(seq) if q.instrument == QuestionInstrument.validity]


def test_empty_validity_returns_base_unchanged() -> None:
    base = _base(30)
    out = interleave_validity(base, [], seed=1)
    assert out == base
    assert out is not base  # a copy, not the same list


def test_nothing_is_dropped_and_base_order_is_preserved() -> None:
    base, validity = _base(120), _validity(25)
    out = interleave_validity(base, validity, seed=uuid.uuid4().int)

    assert len(out) == 145
    assert [q for q in out if q.instrument == QuestionInstrument.big_five] == base
    assert {id(q) for q in out if q.instrument == QuestionInstrument.validity} == {
        id(q) for q in validity
    }


def test_never_on_the_edges() -> None:
    out = interleave_validity(_base(120), _validity(25), seed=42)
    pos = _positions(out)
    assert min(pos) >= _EDGE_MARGIN
    assert max(pos) <= len(out) - 1 - _EDGE_MARGIN


def test_no_two_validity_items_adjacent() -> None:
    out = interleave_validity(_base(120), _validity(25), seed=7)
    pos = _positions(out)
    gaps = [b - a for a, b in zip(pos, pos[1:])]
    # >= _MIN_BASE_BETWEEN + 1 index-distance == that many base items between
    assert min(gaps) >= _MIN_BASE_BETWEEN + 1


def test_not_a_fixed_every_nth_pattern() -> None:
    out = interleave_validity(_base(120), _validity(25), seed=7)
    gaps = {b - a for a, b in zip(_positions(out), _positions(out)[1:])}
    assert len(gaps) > 1  # spacing varies — not "every 5th is a trap"


def test_deterministic_on_seed() -> None:
    aid = uuid.uuid4().int
    a = interleave_validity(_base(120), _validity(25), seed=aid)
    b = interleave_validity(_base(120), _validity(25), seed=aid)
    assert [q.text for q in a] == [q.text for q in b]


def test_different_assessments_get_different_batteries() -> None:
    a = interleave_validity(_base(120), _validity(25), seed=1)
    b = interleave_validity(_base(120), _validity(25), seed=2)
    assert [q.text for q in a] != [q.text for q in b]


def test_short_run_degrades_without_crashing() -> None:
    base, validity = _base(12), _validity(5)
    out = interleave_validity(base, validity, seed=3)
    assert len(out) == 17
    assert [q for q in out if q.instrument == QuestionInstrument.big_five] == base
    assert len(_positions(out)) == 5
