"""Admin: АСТУР bank versions (draft → validate → publish → immutable) and
per-item analytics (PRO-427)."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.astur_bank_version import AsturBankVersion, AsturBankVersionStatus
from app.models.astur_run import AsturRun
from app.models.user import User
from app.schemas.astur_admin import (
    AsturBankDiffResponse,
    AsturBankVersionDetail,
    AsturBankVersionList,
    AsturBankVersionSummary,
    PublishAsturDraftRequest,
    UpdateAsturDraftRequest,
)
from app.services.astur import analytics, bank_versions
from app.services.astur.bank_validation import KEY_DEFINING_FIELDS

router = APIRouter(tags=["admin-astur"])

AgeBand = Literal["under_14", "14_15", "16_17", "18_plus", "unknown"]


def _item_count(document: dict) -> int:
    return sum(len(s.get("items", [])) for s in document.get("subtests", []))


async def _attempt_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await db.execute(select(AsturRun.bank_version_id, func.count()).group_by(AsturRun.bank_version_id))
    return {version_id: count for version_id, count in rows.all()}


def _summary(row: AsturBankVersion, attempt_count: int = 0) -> dict:
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status.value,
        "content_hash": row.content_hash,
        "based_on_id": row.based_on_id,
        "notes": row.notes,
        "item_count": _item_count(row.document),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "published_at": row.published_at,
        "attempt_count": attempt_count,
    }


def _key_changed_items(document: dict, base_document: dict) -> list[str]:
    base_items = {i.get("item_id"): i for s in base_document.get("subtests", []) for i in s.get("items", [])}
    changed = []
    for subtest in document.get("subtests", []):
        for item in subtest.get("items", []):
            previous = base_items.get(item.get("item_id"))
            if previous is not None and any(item.get(f) != previous.get(f) for f in KEY_DEFINING_FIELDS):
                changed.append(item["item_id"])
    return changed


async def _detail(db: AsyncSession, row: AsturBankVersion) -> AsturBankVersionDetail:
    counts = await _attempt_counts(db)
    issues, key_changed = [], []
    if row.status == AsturBankVersionStatus.draft:
        # Confirmation-required issues are listed separately (key_changed_item_ids)
        # — confirming is part of publishing, not something to "fix".
        issues = [
            i.as_dict()
            for i in await bank_versions.validate_version(db, row)
            if i.code != "key_confirmation_required"
        ]
        if row.based_on_id is not None:
            base = await db.get(AsturBankVersion, row.based_on_id)
            key_changed = _key_changed_items(row.document, base.document) if base else []
    return AsturBankVersionDetail(
        **_summary(row, counts.get(row.id, 0)),
        document=row.document,
        issues=issues,
        key_changed_item_ids=key_changed,
        has_changes=await bank_versions.has_changes(db, row),
    )


@router.get("/bank-versions", response_model=AsturBankVersionList)
async def list_bank_versions(
    _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
) -> AsturBankVersionList:
    counts = await _attempt_counts(db)
    rows = await bank_versions.list_versions(db)
    return AsturBankVersionList(items=[AsturBankVersionSummary(**_summary(r, counts.get(r.id, 0))) for r in rows])


@router.get("/bank-versions/{version_id}", response_model=AsturBankVersionDetail)
async def get_bank_version(
    version_id: uuid.UUID, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
) -> AsturBankVersionDetail:
    return await _detail(db, await bank_versions.get_version(db, version_id))


@router.post("/bank-versions/draft", response_model=AsturBankVersionDetail, status_code=status.HTTP_201_CREATED)
async def create_draft(
    admin: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
) -> AsturBankVersionDetail:
    """Branches a draft off the latest published version; returns the open
    draft if one already exists."""
    return await _detail(db, await bank_versions.create_draft(db, admin_id=admin.id))


@router.put("/bank-versions/{version_id}", response_model=AsturBankVersionDetail)
async def update_draft(
    version_id: uuid.UUID,
    data: UpdateAsturDraftRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AsturBankVersionDetail:
    row = await bank_versions.update_draft(db, version_id, document=data.document, notes=data.notes)
    return await _detail(db, row)


@router.delete("/bank-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    version_id: uuid.UUID, _: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)
) -> Response:
    await bank_versions.delete_draft(db, version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bank-versions/{version_id}/publish", response_model=AsturBankVersionDetail)
async def publish_draft(
    version_id: uuid.UUID,
    data: PublishAsturDraftRequest,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AsturBankVersionDetail:
    """Validates and freezes the draft as the next version. 422 with the
    full issue list if anything is wrong (incl. unconfirmed key changes)."""
    row = await bank_versions.publish(
        db, version_id, admin_id=admin.id, confirmed_item_ids=set(data.confirmed_item_ids)
    )
    return await _detail(db, row)


@router.get("/bank-versions/{version_id}/diff", response_model=AsturBankDiffResponse)
async def diff_bank_version(
    version_id: uuid.UUID,
    against: uuid.UUID | None = Query(default=None, description="Defaults to the version this one is based on"),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AsturBankDiffResponse:
    row = await bank_versions.get_version(db, version_id)
    base_id = against or row.based_on_id
    if base_id is None:
        return AsturBankDiffResponse(from_version=None, to_version=row.version, changes=[])
    base = await bank_versions.get_version(db, base_id)
    return AsturBankDiffResponse(
        from_version=base.version,
        to_version=row.version,
        changes=bank_versions.diff_documents(base.document, row.document),
    )


@router.get("/bank-versions/{version_id}/analytics")
async def bank_version_analytics(
    version_id: uuid.UUID,
    age_band: AgeBand | None = None,
    grade: int | None = Query(default=None, ge=1, le=12),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-item analytics of completed attempts on one published version —
    for spotting too-easy, confusing or broken items. Not a norm."""
    row = await bank_versions.get_version(db, version_id)
    if row.status != AsturBankVersionStatus.published:
        return {"bank_version": None, "attempts": 0, "filters": {}, "age_bands": {}, "grades": {}, "subtests": []}
    return await analytics.item_analytics(db, bank_version_id=version_id, band=age_band, grade=grade)
