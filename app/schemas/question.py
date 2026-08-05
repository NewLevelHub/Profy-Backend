import uuid

from pydantic import BaseModel

from app.models.question import BigFiveDomain, HollandType, QuestionInstrument


class QuestionResponse(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    riasec_type: HollandType | None
    bigfive_domain: BigFiveDomain | None
    text: str
    order: int

    model_config = {"from_attributes": True}
