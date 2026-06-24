import uuid

from pydantic import BaseModel

from app.models.question import QuestionBlock


class AnswerItem(BaseModel):
    question_id: uuid.UUID
    selected_option_index: int


class SaveAnswersRequest(BaseModel):
    block: QuestionBlock
    answers: list[AnswerItem]


class SaveAnswersResponse(BaseModel):
    block: QuestionBlock
    scores: dict[str, float]
