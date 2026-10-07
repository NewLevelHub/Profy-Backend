"""Admin contracts for АСТУР bank versions and item analytics (PRO-427)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AsturBankIssue(BaseModel):
    code: str
    message: str
    subtest: str | None = None
    item_id: str | None = None
    field: str | None = None


class AsturBankVersionSummary(BaseModel):
    id: uuid.UUID
    version: int | None
    status: Literal["draft", "published"]
    content_hash: str | None
    based_on_id: uuid.UUID | None
    notes: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    # Completed + open attempts pinned to this version.
    attempt_count: int = 0


class AsturBankVersionDetail(AsturBankVersionSummary):
    document: dict
    # Draft only: current validation result against its base version.
    issues: list[AsturBankIssue] = Field(default_factory=list)
    # Draft only: items whose key-defining fields differ from the base.
    key_changed_item_ids: list[str] = Field(default_factory=list)
    # Draft only: False while the draft equals its base (nothing to publish).
    has_changes: bool = True


class AsturBankVersionList(BaseModel):
    items: list[AsturBankVersionSummary]


class UpdateAsturDraftRequest(BaseModel):
    document: dict
    notes: str | None = Field(default=None, max_length=2000)


class PublishAsturDraftRequest(BaseModel):
    # Item ids whose changed key the publisher explicitly confirms.
    confirmed_item_ids: list[str] = Field(default_factory=list)


class AddAsturSynonymRequest(BaseModel):
    item_id: str
    tier: Literal["score_2", "score_1"]
    locale: Literal["ru", "kk"]
    text: str = Field(min_length=1, max_length=200)


class AsturBankDiffEntry(BaseModel):
    kind: Literal["added", "removed", "changed", "subtest_changed", "bank_changed"]
    subtest: str | None
    item_id: str | None
    fields: list[str]


class AsturBankDiffResponse(BaseModel):
    from_version: int | None
    to_version: int | None
    changes: list[AsturBankDiffEntry]
