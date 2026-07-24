import uuid
from typing import Literal

from pydantic import BaseModel, Field

FeedbackRating = Literal["good", "neutral", "bad"]
FeedbackContext = Literal["roadmap"]


class ProductFeedbackCreateRequest(BaseModel):
    context: FeedbackContext
    overall_rating: FeedbackRating
    # Per-aspect axes — optional at the schema level so older/partial
    # clients don't 422, though the current frontend always sends all four.
    questions_rating: FeedbackRating | None = None
    result_match_rating: FeedbackRating | None = None
    plan_usefulness_rating: FeedbackRating | None = None
    design_rating: FeedbackRating | None = None
    message: str | None = Field(default=None, max_length=2000)
    assessment_id: uuid.UUID | None = None
    direction_slug: str | None = None


class ProductFeedbackCreateResponse(BaseModel):
    status: Literal["recorded"] = "recorded"


class ProductFeedbackStatusResponse(BaseModel):
    submitted: bool
