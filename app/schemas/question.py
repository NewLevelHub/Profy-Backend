import uuid

from pydantic import BaseModel

from app.models.question import HollandType


class QuestionResponse(BaseModel):
    id: uuid.UUID
    riasec_type: HollandType
    text: str
    order: int

    model_config = {"from_attributes": True}
