import uuid

from pydantic import BaseModel, Field


class AnswerItem(BaseModel):
    question_id: uuid.UUID
    # Structural envelope for the union of all numeric scales. The real
    # domain depends on the question's instrument (e.g. 1/2 for binary,
    # 0..3 for abilities, 1..5 for RIASEC) and is enforced server-side after
    # the question is loaded in answer_validation.validate_answer_value.
    value: int = Field(ge=0, le=5)


class SubmitAnswersRequest(BaseModel):
    answers: list[AnswerItem]


class SubmitAnswersResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
