import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.akinator_session import RevealLeaf


class ResultAxisHighlight(BaseModel):
    code: str
    label_ru: str
    direction_value: int


class AkinatorResultResponse(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str
    direction_name: str
    direction_description: str
    message: str
    matched_axes: list[ResultAxisHighlight]
    backups: list[RevealLeaf]
    created_at: datetime
