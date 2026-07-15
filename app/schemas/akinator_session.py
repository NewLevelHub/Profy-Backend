import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AkinatorAnswerRequest(BaseModel):
    question_id: uuid.UUID
    selected_option_index: int | None = Field(default=None, ge=0)  # null = "не знаю"


class AkinatorOption(BaseModel):
    index: int
    text: str


class NextQuestionResponse(BaseModel):
    type: Literal["next_question"] = "next_question"
    question_id: uuid.UUID
    text: str
    options: list[AkinatorOption]


class RevealLeaf(BaseModel):
    slug: str
    name: str


class RevealResponse(BaseModel):
    type: Literal["reveal"] = "reveal"
    status: Literal["single", "cluster"]
    leaves: list[RevealLeaf]
    backups: list[RevealLeaf] = Field(default_factory=list)
    message: str


AkinatorTurnResponse = Annotated[
    NextQuestionResponse | RevealResponse, Field(discriminator="type")
]


class AkinatorFeedbackRequest(BaseModel):
    liked: bool
    note: str | None = None


class AkinatorFeedbackResponse(BaseModel):
    status: Literal["recorded"] = "recorded"
