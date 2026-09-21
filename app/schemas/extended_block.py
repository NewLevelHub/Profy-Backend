"""Extended block assignment contract (PRO-338, post-Ф4.1 follow-up)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ExtendedBlockLiteral = Literal["belbin", "astur"]


class AssignExtendedBlockRequest(BaseModel):
    block: ExtendedBlockLiteral

    model_config = {"extra": "forbid"}


class ExtendedBlockAssignmentResponse(BaseModel):
    block: ExtendedBlockLiteral
    assigned_at: datetime
    # Derived from whether belbin_runs/astur_runs has a row for this
    # assessment_id — never a separate stored flag (see the model's own
    # docstring for why).
    completed: bool


class ExtendedBlocksResponse(BaseModel):
    assignments: list[ExtendedBlockAssignmentResponse]
