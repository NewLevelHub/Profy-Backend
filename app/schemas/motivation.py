import uuid

from pydantic import BaseModel


class MotivationStatementResponse(BaseModel):
    id: uuid.UUID
    triplet_index: int
    order: int
    text: str
    # `category` intentionally omitted — showing it would let the student
    # see which card belongs to which value, turning forced-choice into a
    # social-desirability pick instead of an honest trade-off.

    model_config = {"from_attributes": True}


class MotivationTripletResponse(BaseModel):
    triplet_index: int
    statements: list[MotivationStatementResponse]


class MotivationAnswerItem(BaseModel):
    triplet_index: int
    most_statement_id: uuid.UUID
    least_statement_id: uuid.UUID


class SubmitMotivationRequest(BaseModel):
    answers: list[MotivationAnswerItem]


class SubmitMotivationResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
