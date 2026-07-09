"""Direction-fit inquiry: probing questions about a chosen direction + a verdict.

Flow: pick a direction → GET questions (AI) → answer on a 5-point scale →
POST answers → short AI verdict (fit + readiness). middle/senior only.
"""
from pydantic import BaseModel, Field


class DirectionQuestion(BaseModel):
    text: str
    kind: str  # "interest" | "readiness"


class DirectionQuestionsResponse(BaseModel):
    direction_slug: str
    direction_name: str
    scale: list[str]                 # 5-point Likert labels for the client to render
    questions: list[DirectionQuestion]


class DirectionVerdictRequest(BaseModel):
    # One selected scale index (0..4) per question, in order.
    answers: list[int] = Field(..., min_length=1)


class DirectionVerdictResponse(BaseModel):
    direction_slug: str
    readiness: str                   # "Высокая готовность" | "Средняя готовность" | "Стоит присмотреться"
    fit_summary: str
    note: str
