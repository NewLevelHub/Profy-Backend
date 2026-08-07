from typing import Literal

from pydantic import BaseModel


class MotivationPairItem(BaseModel):
    pair_index: int
    text_a: str
    text_b: str
    # category_a/category_b intentionally omitted — same anti-social-
    # desirability reasoning as MotivationStatementResponse's dropped
    # `category` (app/schemas/motivation.py): showing which side maps to
    # which value would turn an honest camp pick into a status pick.

    model_config = {"from_attributes": True}


class PairIntensityAnswer(BaseModel):
    pair_index: int
    chosen_side: Literal["a", "b"]
    intensity: Literal["high", "medium"]


class SubmitMotivationPairRequest(BaseModel):
    answers: list[PairIntensityAnswer]


class SubmitMotivationPairResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
