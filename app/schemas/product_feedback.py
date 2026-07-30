import uuid
from typing import Literal

from pydantic import BaseModel, Field

FeedbackContext = Literal["roadmap"]


class ProductFeedbackCreateRequest(BaseModel):
    context: FeedbackContext
    # Raw 1-5 picker values, sent as-is — the good/neutral/bad category
    # stored on the row is now derived server-side (see
    # product_feedback_service.create_feedback), not collapsed by the
    # frontend before submitting, so admin analytics can average the real
    # number instead of approximating a category back into one.
    overall_score: int = Field(ge=1, le=5)
    # Per-aspect axes — optional at the schema level so older/partial
    # clients don't 422, though the current frontend always sends all four.
    questions_score: int | None = Field(default=None, ge=1, le=5)
    result_match_score: int | None = Field(default=None, ge=1, le=5)
    plan_usefulness_score: int | None = Field(default=None, ge=1, le=5)
    design_score: int | None = Field(default=None, ge=1, le=5)
    message: str | None = Field(default=None, max_length=2000)
    assessment_id: uuid.UUID | None = None
    direction_slug: str | None = None


class ProductFeedbackCreateResponse(BaseModel):
    status: Literal["recorded"] = "recorded"


class ProductFeedbackStatusResponse(BaseModel):
    submitted: bool
