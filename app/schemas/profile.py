import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem


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
    # Optional so the old two-step onboarding flow (POST /profile then a
    # separate POST /profile/artifacts) keeps working byte-for-byte: clients
    # that never send this field behave exactly as before. `None` means "the
    # caller isn't managing artifacts here at all" (skip artifact writes
    # entirely); `[]` means "save zero artifacts" (harmless no-op for a
    # brand-new profile, but goes through the same code path). See
    # app/routers/profile.py::create_profile for how this is applied
    # atomically alongside the Profile row.
    artifacts: list[ArtifactItem] | None = None


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
    # Optional, same semantics as ProfileCreateRequest.artifacts: `None` means
    # "caller isn't managing artifacts here, leave them untouched"; any list
    # (including `[]`) replaces the profile's artifacts wholesale via the
    # same delete-then-insert as the standalone POST /profile/artifacts.
    artifacts: list[ArtifactItem] | None = None


class ProfileResponse(BaseModel):
    """Returned by GET, POST, and PUT /api/v1/profile alike — `artifacts` is
    always present (empty list if none exist) so no client needs a
    follow-up GET /profile/artifacts just to render the profile page.
    Callers populate it explicitly (there's no ORM relationship backing it);
    see app/routers/profile.py.
    """

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
    artifacts: list[ArtifactItem] = []

    model_config = {"from_attributes": True}
