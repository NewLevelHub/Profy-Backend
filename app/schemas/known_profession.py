import uuid
from typing import Literal

from pydantic import BaseModel, Field


class KnownProfessionQuestionOption(BaseModel):
    text: str
    fit_score: Literal[0, 1, 2]


class KnownProfessionQuestion(BaseModel):
    id: str
    kind: Literal["situational", "subject", "commitment"]
    text: str
    options: list[KnownProfessionQuestionOption]


class KnownProfessionQuizResponse(BaseModel):
    leaf_slug: str
    questions: list[KnownProfessionQuestion]


class KnownProfessionFinalizeRequest(BaseModel):
    direction_slug: str
    # question_id -> selected option index
    answers: dict[str, int] = Field(default_factory=dict)


class KnownProfessionFinalizeResponse(BaseModel):
    assessment_id: uuid.UUID
    percent: int
    verdict: Literal["strong", "partial", "weak"]
