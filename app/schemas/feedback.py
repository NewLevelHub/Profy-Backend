import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProductFeedbackCreate(BaseModel):
    """Submit body for the post-report 3-question survey (TZ_Profi.md §28.4)."""

    assessment_id: uuid.UUID
    relevance_score: int = Field(ge=1, le=5)
    helpful_sections: list[str] = Field(default_factory=list, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)


class ProductFeedbackResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID | None
    relevance_score: int
    helpful_sections: list[str]
    comment: str | None
    created_at: datetime
