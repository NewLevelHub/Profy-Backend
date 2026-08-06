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
