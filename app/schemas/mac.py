"""Схемы пользовательской части МАК (PRO-315/316). Никакого скоринга —
только конфиг упражнений, выдача карт, приём дословных ответов."""
import uuid

from pydantic import BaseModel, Field, field_validator


class MacExerciseItem(BaseModel):
    id: uuid.UUID
    code: str
    order: int
    title: str
    stimulus_question: str
    draw_mode: str  # "blind" | "open"
    spread_size: int | None
    pick_count: int
    followup_questions: list[str]

    model_config = {"from_attributes": True}


class MacSessionResponse(BaseModel):
    session_id: uuid.UUID
    completed: bool
    exercises: list[MacExerciseItem]


class MacCardOut(BaseModel):
    id: uuid.UUID
    # Absolute URL (STORAGE_PUBLIC_BASE_URL + mac_cards.image_path) — built
    # by mac_service, never `.model_validate()`'d straight off the ORM row,
    # since the client must never see a bare storage key. See
    # app/integrations/storage/urls.py::build_public_url.
    image_url: str
    kind: str


class MacSpreadResponse(BaseModel):
    cards: list[MacCardOut]
    pick_count: int


class SubmitMacResponseRequest(BaseModel):
    session_id: uuid.UUID
    exercise_id: uuid.UUID
    card_ids: list[uuid.UUID] = Field(min_length=1)
    # Наводящие ответы — по одному на каждый followup_questions[i]; пустая
    # строка недопустима (AC PRO-315: «поле не пустое»).
    followup_answers: list[str] = Field(min_length=1)
    subject: str | None = None  # E4 only
    time_spent_ms: int = Field(ge=0, default=0)
    revision_count: int = Field(ge=0, default=0)

    model_config = {"extra": "forbid"}

    @field_validator("followup_answers")
    @classmethod
    def _no_blank_answers(cls, v: list[str]) -> list[str]:
        if any(not a.strip() for a in v):
            raise ValueError("followup answers must not be blank")
        return v


class SubmitMacResponseResponse(BaseModel):
    response_id: uuid.UUID
    session_completed: bool
