"""Server-side answer domains for question-based instruments.

The request schema deliberately accepts the union of all numeric scales. A
value can only be validated after its question has been loaded and the
instrument is known, so the actual domain rules live here rather than in the
Pydantic model.
"""

from fastapi import status

from app.errors import AppError
from app.i18n.catalog import key as i18n_key
from app.models.question import QuestionInstrument


# Keep the retired Big Five domain documented for historical data and any
# offline validation. The current answers endpoint rejects Big Five question
# IDs before this validation because they are not part of the active battery.
ANSWER_VALUES_BY_INSTRUMENT: dict[QuestionInstrument, frozenset[int]] = {
    QuestionInstrument.riasec: frozenset(range(1, 6)),
    QuestionInstrument.big_five: frozenset(range(1, 6)),
    QuestionInstrument.professional_types_abilities: frozenset(range(0, 4)),
    QuestionInstrument.eysenck: frozenset({1, 2}),
    QuestionInstrument.elers: frozenset({1, 2}),
    QuestionInstrument.boyko_empathy: frozenset({1, 2}),
    QuestionInstrument.kondash_anxiety: frozenset(range(0, 5)),
}

# These questions encode a forced choice between two question IDs. Their
# synthetic stored values (picked=5, other=1) are an implementation detail of
# question_pair_service and must not be accepted from the scalar endpoint.
PAIR_ONLY_INSTRUMENTS = frozenset({QuestionInstrument.professional_types})


def validate_answer_value(instrument: QuestionInstrument, value: int) -> None:
    """Reject values that are not in the question instrument's real scale."""
    if instrument in PAIR_ONLY_INSTRUMENTS:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="question_requires_pair_answer",
            detail=i18n_key("api_errors", "question_requires_pair_answer"),
        )

    allowed_values = ANSWER_VALUES_BY_INSTRUMENT.get(instrument)
    if allowed_values is None:
        # Every enum member must be deliberately classified. A new instrument
        # without a declared domain must never inherit the broad request range.
        raise RuntimeError(
            f"No answer domain configured for instrument {instrument.value}"
        )

    if value not in allowed_values:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="answer_value_invalid_for_instrument",
            detail=i18n_key(
                "api_errors", "answer_value_invalid_for_instrument"
            ).format(
                value=value,
                instrument=instrument.value,
                allowed=", ".join(str(item) for item in sorted(allowed_values)),
            ),
        )
