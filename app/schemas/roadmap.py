import uuid

from pydantic import BaseModel


class RoadmapTask(BaseModel):
    text: str
    category: str
    priority: int


class RoadmapMilestone(BaseModel):
    horizon: str
    title: str
    tasks: list[RoadmapTask]


class RoadmapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    goal: str
    milestones: list[RoadmapMilestone]

    model_config = {"from_attributes": True}
