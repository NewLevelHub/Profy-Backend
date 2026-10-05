import uuid

from pydantic import BaseModel, field_validator

from app.schemas.validation import ensure_unique


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

    @field_validator("answers")
    @classmethod
    def triplet_indexes_are_unique(
        cls, answers: list[MotivationAnswerItem]
    ) -> list[MotivationAnswerItem]:
        ensure_unique(
            (item.triplet_index for item in answers),
            error_code="duplicate_triplet_indexes",
        )
        return answers


class SubmitMotivationResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
