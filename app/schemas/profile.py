import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.certificate import CertificateItem

# Letters (any script) plus space/hyphen/apostrophe for names like
# "Анна-Мария" or "O'Brien" — no digits, no other symbols. Mirrors the
# frontend's NAME_PATTERN (useProfileSetup.ts). pydantic-core's `pattern`
# compiles with Rust's `regex` crate, which supports \p{L} natively.
NAME_PATTERN = r"^[\p{L}\s'-]+$"

# NOTE: the `profiles.gpa_value` / `gpa_scale` columns still exist (see
# app/models/profile.py) but are no longer part of the profile API — GPA was
# dropped from the product surface (pro-236). These schemas neither accept
# nor return them; only exam certificates are collected now.


class ProfileCreateRequest(BaseModel):
    # min/max_length and pattern mirror the frontend's NAME_MIN_LENGTH/
    # NAME_MAX_LENGTH/NAME_PATTERN (useProfileSetup.ts); max stays well
    # under the `profiles.name` column's String(255) cap, so an invalid or
    # over-limit name is rejected here with a clean 422 rather than
    # reaching the DB layer.
    name: str = Field(..., min_length=3, max_length=60, pattern=NAME_PATTERN)
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
    # Same optional/atomic-write contract as `artifacts`, but backed by
    # app/services/certificate_service.py instead. `None` = not managing
    # certificates here; any list (including `[]`) replaces them wholesale.
    certificates: list[CertificateItem] | None = None


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=60, pattern=NAME_PATTERN)
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
    # Same semantics as `artifacts`, backed by certificate_service instead.
    certificates: list[CertificateItem] | None = None


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
    certificates: list[CertificateItem] = []

    model_config = {"from_attributes": True}
