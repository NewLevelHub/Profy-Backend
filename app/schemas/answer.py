import uuid

from pydantic import BaseModel

from app.models.question import QuestionBlock


class AnswerItem(BaseModel):
    question_id: uuid.UUID
    selected_option_index: int


class AnswersBulkRequest(BaseModel):
    block: QuestionBlock
    answers: list[AnswerItem]


class AnswersResponse(BaseModel):
    saved: int
    current_block: int
