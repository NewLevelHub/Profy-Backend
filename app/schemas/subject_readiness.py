import uuid
from datetime import datetime

from pydantic import BaseModel


class SubjectQuestionOption(BaseModel):
    text: str
    index: int


class SubjectQuestionOut(BaseModel):
    """Question shown to the client — no `score` on options and no indication
    of whether this subject is one of the direction's required ones or the
    noise subject (see subject_readiness_service.get_or_create_questions)."""

    id: uuid.UUID
    subject: str
    kind: str
    text: str
    options: list[SubjectQuestionOption]


class SubjectAnswerIn(BaseModel):
    question_id: uuid.UUID
    selected_option_index: int


class SubmitSubjectAnswersRequest(BaseModel):
    answers: list[SubjectAnswerIn]


class SubjectScoreItem(BaseModel):
    subject: str
    level: int
    interest: int
    is_strength: bool


class SubjectReadinessResult(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    direction_slug: str
    subject_scores: list[SubjectScoreItem]
    completed_at: datetime

    model_config = {"from_attributes": True}
