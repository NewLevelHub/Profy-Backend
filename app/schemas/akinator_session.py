import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AkinatorAnswerRequest(BaseModel):
    question_id: uuid.UUID
    selected_option_index: int | None = Field(default=None, ge=0)  # null = "не знаю"
    # "Не интересует" — a distinct, stronger signal than "не знаю" (null
    # selected_option_index with disinterested=False). Mutually exclusive
    # with selected_option_index; see akinator_session_service.submit_answer.
    disinterested: bool = False


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
    # Parent section/category name (e.g. "Медицина и здоровье") — gives the
    # user a broader "направление" to anchor on alongside the specific
    # profession, instead of just a bare, possibly unfamiliar job title.
    direction: str
    description: str = ""
    professions: list[str] = Field(default_factory=list)


class RevealResponse(BaseModel):
    type: Literal["reveal"] = "reveal"
    status: Literal["single", "cluster", "inconclusive"]
    leaves: list[RevealLeaf]
    backups: list[RevealLeaf] = Field(default_factory=list)
    message: str
    # Only populated for status="inconclusive" — friendly axis-strength
    # labels (see akinator_report_service.summarize_strengths), the honest
    # fallback when the question ceiling was hit without a confident answer.
    strengths: list[str] = Field(default_factory=list)


AkinatorTurnResponse = Annotated[
    NextQuestionResponse | RevealResponse, Field(discriminator="type")
]


class AkinatorFeedbackRequest(BaseModel):
    liked: bool
    note: str | None = None
    # Which leaf the user actually accepted — set when feedback follows a
    # per-leaf simulation accept (see submit_simulation_outcome on the
    # frontend side). Falls back to the engine's own top belief when absent,
    # so older callers keep working.
    direction_slug: str | None = None


class AkinatorFeedbackResponse(BaseModel):
    status: Literal["recorded"] = "recorded"


class AkinatorResolveRequest(BaseModel):
    question_id: uuid.UUID | None = None
    selected_option_index: int | None = Field(default=None, ge=0)


class AkinatorRejectAllRequest(BaseModel):
    """Batch reject — the "none of these fit" footer action, rejecting every
    leaf currently shown on the reveal in one call. See
    akinator_session_service.reject_leaves."""
    leaf_slugs: list[str]
