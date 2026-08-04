import uuid

from pydantic import BaseModel, Field


class AnswerItem(BaseModel):
    question_id: uuid.UUID
    value: int = Field(ge=1, le=5)


class SubmitAnswersRequest(BaseModel):
    answers: list[AnswerItem]


class SubmitAnswersResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
