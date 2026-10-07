import uuid

from pydantic import BaseModel, field_validator

from app.models.question import BigFiveDomain, HollandType, QuestionInstrument
from app.schemas.validation import ensure_unique


class QuestionPairOption(BaseModel):
    id: uuid.UUID
    text: str
    icon: str | None
    riasec_type: HollandType | None
    bigfive_domain: BigFiveDomain | None

    model_config = {"from_attributes": True}


class QuestionPairItem(BaseModel):
    pair_index: int
    instrument: QuestionInstrument
    frame: str | None
    # min(option_a's, option_b's) underlying Question.order — lets the
    # frontend interleave a pair into its position in the plain-Likert
    # sequence. See buildDisplaySequence.ts.
    display_order: int
    option_a: QuestionPairOption
    option_b: QuestionPairOption


class PairAnswerItem(BaseModel):
    pair_index: int
    picked_question_id: uuid.UUID


class SubmitPairAnswersRequest(BaseModel):
    answers: list[PairAnswerItem]

    @field_validator("answers")
    @classmethod
    def pair_indexes_are_unique(
        cls, answers: list[PairAnswerItem]
    ) -> list[PairAnswerItem]:
        ensure_unique(
            (item.pair_index for item in answers),
            error_code="duplicate_pair_indexes",
        )
        return answers


class SubmitPairAnswersResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
