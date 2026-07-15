import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.axes import AXIS_CODES
from app.models.akinator_question import QuestionAgeVariant, QuestionKind


class AkinatorQuestionOption(BaseModel):
    text: str
    axis_weights: dict[str, int] = {}

    @field_validator("axis_weights")
    @classmethod
    def axis_weights_keys_must_be_known(cls, value: dict[str, int]) -> dict[str, int]:
        unknown = sorted(set(value) - AXIS_CODES)
        if unknown:
            raise ValueError(f"Unknown axis code(s): {unknown}")
        return value


class AkinatorQuestionBase(BaseModel):
    kind: QuestionKind
    depth: int
    age_variant: QuestionAgeVariant = QuestionAgeVariant.both
    text: str
    text_junior: str | None = None
    options: list[AkinatorQuestionOption]
    resolves_pair: list[str] | None = None
    is_active: bool = True
    order: int = 0


class AkinatorQuestionCreate(AkinatorQuestionBase):
    pass


class AkinatorQuestionResponse(AkinatorQuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
