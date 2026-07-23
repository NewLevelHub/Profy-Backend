import uuid
from typing import Literal

from pydantic import BaseModel, Field

FeedbackRating = Literal["good", "neutral", "bad"]
FeedbackContext = Literal["roadmap"]


class ProductFeedbackCreateRequest(BaseModel):
    context: FeedbackContext
    rating: FeedbackRating
    message: str | None = Field(default=None, max_length=2000)
    assessment_id: uuid.UUID | None = None
    direction_slug: str | None = None


class ProductFeedbackCreateResponse(BaseModel):
    status: Literal["recorded"] = "recorded"


class ProductFeedbackStatusResponse(BaseModel):
    submitted: bool
