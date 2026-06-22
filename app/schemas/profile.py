import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProfileCreateRequest(BaseModel):
    name: str
    age: int = Field(..., ge=6, le=18)
    grade: int = Field(..., ge=1, le=12)
    city: str
    country: str
    language: str
    subjects_liked: list[str] = []
    subjects_disliked: list[str] = []
    subjects_easy: list[str] = []
    subjects_hard: list[str] = []


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    age: int | None = Field(None, ge=6, le=18)
    grade: int | None = Field(None, ge=1, le=12)
    city: str | None = None
    country: str | None = None
    language: str | None = None
    subjects_liked: list[str] | None = None
    subjects_disliked: list[str] | None = None
    subjects_easy: list[str] | None = None
    subjects_hard: list[str] | None = None


class ProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    age: int
    grade: int
    city: str
    country: str
    language: str
    subjects_liked: list[str]
    subjects_disliked: list[str]
    subjects_easy: list[str]
    subjects_hard: list[str]
    age_group: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
