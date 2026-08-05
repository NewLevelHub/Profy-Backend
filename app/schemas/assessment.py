import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.assessment import AssessmentGoal, AssessmentStatus


class AssessmentCreateRequest(BaseModel):
    goal: AssessmentGoal


class AssessmentResponse(BaseModel):
    id: uuid.UUID
    goal: AssessmentGoal
    status: AssessmentStatus
    answered_count: int
    total_questions: int
    motivation_answered_count: int
    motivation_total: int
    created_at: datetime

    model_config = {"from_attributes": True}
