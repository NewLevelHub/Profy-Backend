import uuid
from pydantic import BaseModel, Field
from typing import Literal
from app.schemas.akinator_session import AkinatorTurnResponse


class SimulationStepOption(BaseModel):
    text: str
    consequence: str


class SimulationStep(BaseModel):
    text: str
    options: list[SimulationStepOption]


class SimulationDetailResponse(BaseModel):
    leaf_slug: str
    steps: list[SimulationStep]


class SimulationSubmitRequest(BaseModel):
    accepted: bool
    answers: list[int] = Field(default_factory=list)


class SimulationSubmitResponse(BaseModel):
    status: Literal["recorded"] = "recorded"
    akinator_turn: AkinatorTurnResponse | None = None
