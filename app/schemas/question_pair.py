import uuid

from pydantic import BaseModel

from app.models.question import BigFiveDomain, HollandType, QuestionInstrument


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
    # sequence (middle only; junior's screen ignores it and just uses
    # pair_index order). See buildDisplaySequence.ts.
    display_order: int
    option_a: QuestionPairOption
    option_b: QuestionPairOption


class PairAnswerItem(BaseModel):
    pair_index: int
    picked_question_id: uuid.UUID


class SubmitPairAnswersRequest(BaseModel):
    answers: list[PairAnswerItem]


class SubmitPairAnswersResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
