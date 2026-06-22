import uuid

from pydantic import BaseModel

from app.models.question import QuestionBlock


class QuestionOption(BaseModel):
    text: str
    index: int


class QuestionResponse(BaseModel):
    id: uuid.UUID
    block: QuestionBlock
    text: str
    options: list[QuestionOption]
