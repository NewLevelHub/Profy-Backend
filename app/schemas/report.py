from pydantic import BaseModel


class DirectionMatch(BaseModel):
    direction: str
    score: int


class ReportResponse(BaseModel):
    assessment_id: str
    normalized_scores: dict[str, float]
    strengths: list[str]
    directions: list[DirectionMatch]
