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
    secondary_goals: list[AssessmentGoal] = []
    goal_changed_count: int = 0
    belbin_completed: bool = False
    astur_completed: bool = False

    model_config = {"from_attributes": True}


class SavedMotivationAnswer(BaseModel):
    most_statement_id: uuid.UUID
    least_statement_id: uuid.UUID


class SavedAnswersResponse(BaseModel):
    """What's already stored for an assessment's main battery and
    motivation — the question / pair / triplet endpoints never echo answers
    back, so without this a client that lost its own copy (new tab, another
    device) showed earlier pages blank on "Назад", and re-sent defaults over
    real answers."""

    # Every stored UserResponse value by question id. Pair options are in
    # here too, as their synthetic picked/other values — clients read only
    # the ids they render as scale items.
    question_values: dict[uuid.UUID, int]
    # pair_index → the picked option's question id.
    pair_picks: dict[int, uuid.UUID]
    # triplet_index → MOST / LEAST statement ids.
    motivation: dict[int, SavedMotivationAnswer]
