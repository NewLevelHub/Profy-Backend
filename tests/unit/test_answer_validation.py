from app.models.question import QuestionInstrument
from app.services.answer_validation import (
    ANSWER_VALUES_BY_INSTRUMENT,
    PAIR_ONLY_INSTRUMENTS,
)


def test_every_question_instrument_has_an_explicit_answer_mode() -> None:
    """A newly added instrument cannot silently inherit the request range."""
    scalar_instruments = set(ANSWER_VALUES_BY_INSTRUMENT)
    pair_instruments = set(PAIR_ONLY_INSTRUMENTS)

    assert scalar_instruments.isdisjoint(pair_instruments)
    assert scalar_instruments | pair_instruments == set(QuestionInstrument)


def test_answer_domains_match_the_methodology_scales() -> None:
    assert ANSWER_VALUES_BY_INSTRUMENT[QuestionInstrument.riasec] == set(
        range(1, 6)
    )
    assert ANSWER_VALUES_BY_INSTRUMENT[
        QuestionInstrument.professional_types_abilities
    ] == set(range(0, 4))
    for instrument in (
        QuestionInstrument.eysenck,
        QuestionInstrument.elers,
        QuestionInstrument.boyko_empathy,
    ):
        assert ANSWER_VALUES_BY_INSTRUMENT[instrument] == {1, 2}
    assert ANSWER_VALUES_BY_INSTRUMENT[
        QuestionInstrument.kondash_anxiety
    ] == set(range(0, 5))
