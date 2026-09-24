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
