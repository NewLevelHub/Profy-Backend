import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.schemas.artifact import ArtifactInput, ArtifactItem
from app.schemas.certificate import CertificateItem
from app.services.age_grade import age_grade_mismatch_message, is_age_grade_compatible

# Letters (any script) plus space/hyphen/apostrophe for names like
# "Анна-Мария" or "O'Brien" — no digits, no other symbols. Mirrors the
# frontend's NAME_PATTERN (useProfileSetup.ts). pydantic-core's `pattern`
# compiles with Rust's `regex` crate, which supports \p{L} natively.
NAME_PATTERN = r"^[\p{L}\s'-]+$"

# A subject is a chip label — preset or the student's own «+ своё». Mirrors
# the frontend's CUSTOM_CHIP_MAX_LENGTH (pages/onboarding/components/AddCustomChip.tsx).
SUBJECT_MAX_LENGTH = 60
# Chips in one subject list. The form offers about twenty presets plus the
# student's own; nobody has more than a dozen.
SUBJECTS_MAX_ITEMS = 50
# Rows a profile can carry: a handful of chips per artifact section, one
# certificate per exam type with room for a retake.
ARTIFACTS_MAX_ITEMS = 100
CERTIFICATES_MAX_ITEMS = 20
# `profiles.city`/`country` are varchar(255), `language` is varchar(50) — a
# longer value used to reach the database and come back as a 500.
PLACE_MAX_LENGTH = 100
LANGUAGE_MAX_LENGTH = 50

Subject = Annotated[str, Field(max_length=SUBJECT_MAX_LENGTH)]

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
    age: int = Field(..., ge=14, le=18)
    grade: int = Field(..., ge=1, le=12)
    city: str = Field(max_length=PLACE_MAX_LENGTH)
    country: str = Field(max_length=PLACE_MAX_LENGTH)
    language: str = Field(max_length=LANGUAGE_MAX_LENGTH)
    subjects_liked: list[Subject] = Field(default_factory=list, max_length=SUBJECTS_MAX_ITEMS)
    subjects_disliked: list[Subject] = Field(default_factory=list, max_length=SUBJECTS_MAX_ITEMS)
    subjects_easy: list[Subject] = Field(default_factory=list, max_length=SUBJECTS_MAX_ITEMS)
    subjects_hard: list[Subject] = Field(default_factory=list, max_length=SUBJECTS_MAX_ITEMS)
    # Optional so the old two-step onboarding flow (POST /profile then a
    # separate POST /profile/artifacts) keeps working byte-for-byte: clients
    # that never send this field behave exactly as before. `None` means "the
    # caller isn't managing artifacts here at all" (skip artifact writes
    # entirely); `[]` means "save zero artifacts" (harmless no-op for a
    # brand-new profile, but goes through the same code path). See
    # app/routers/profile.py::create_profile for how this is applied
    # atomically alongside the Profile row.
    artifacts: list[ArtifactInput] | None = Field(None, max_length=ARTIFACTS_MAX_ITEMS)
    # Same optional/atomic-write contract as `artifacts`, but backed by
    # app/services/certificate_service.py instead. `None` = not managing
    # certificates here; any list (including `[]`) replaces them wholesale.
    certificates: list[CertificateItem] | None = Field(None, max_length=CERTIFICATES_MAX_ITEMS)

    @model_validator(mode="after")
    def _age_matches_grade(self) -> "ProfileCreateRequest":
        if not is_age_grade_compatible(self.age, self.grade):
            raise ValueError(age_grade_mismatch_message(self.age, self.grade))
        return self


class ProfileUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=60, pattern=NAME_PATTERN)
    age: int | None = Field(None, ge=14, le=18)
    grade: int | None = Field(None, ge=1, le=12)
    city: str | None = Field(None, max_length=PLACE_MAX_LENGTH)
    country: str | None = Field(None, max_length=PLACE_MAX_LENGTH)
    language: str | None = Field(None, max_length=LANGUAGE_MAX_LENGTH)
    subjects_liked: list[Subject] | None = Field(None, max_length=SUBJECTS_MAX_ITEMS)
    subjects_disliked: list[Subject] | None = Field(None, max_length=SUBJECTS_MAX_ITEMS)
    subjects_easy: list[Subject] | None = Field(None, max_length=SUBJECTS_MAX_ITEMS)
    subjects_hard: list[Subject] | None = Field(None, max_length=SUBJECTS_MAX_ITEMS)
    # Optional, same semantics as ProfileCreateRequest.artifacts: `None` means
    # "caller isn't managing artifacts here, leave them untouched"; any list
    # (including `[]`) replaces the profile's artifacts wholesale via the
    # same delete-then-insert as the standalone POST /profile/artifacts.
    artifacts: list[ArtifactInput] | None = Field(None, max_length=ARTIFACTS_MAX_ITEMS)
    # Same semantics as `artifacts`, backed by certificate_service instead.
    certificates: list[CertificateItem] | None = Field(None, max_length=CERTIFICATES_MAX_ITEMS)

    @model_validator(mode="after")
    def _age_matches_grade_when_both_sent(self) -> "ProfileUpdateRequest":
        # Partial updates that touch only one of the pair are checked in
        # profile_service against the stored other field (PRO-420).
        if self.age is not None and self.grade is not None:
            if not is_age_grade_compatible(self.age, self.grade):
                raise ValueError(age_grade_mismatch_message(self.age, self.grade))
        return self


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
