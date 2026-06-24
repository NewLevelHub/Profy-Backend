import uuid
from enum import Enum

from pydantic import BaseModel


class GapStatus(str, Enum):
    met = "met"
    not_met = "not_met"
    in_progress = "in_progress"
    unknown = "unknown"


class GapItem(BaseModel):
    requirement: str
    status: GapStatus
    comment: str


class GapAnalysisResponse(BaseModel):
    program_id: uuid.UUID
    met: list[GapItem]
    not_met: list[GapItem]
    in_progress: list[GapItem]
    unknown: list[GapItem]
    readiness_score: float
