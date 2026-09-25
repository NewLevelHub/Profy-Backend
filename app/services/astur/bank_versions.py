"""АСТУР bank versions: `draft → validation → publish → immutable` (PRO-427).

Published versions are immutable, so a parsed `AsturBank` is cached per
version id for the life of the process — scoring and content never re-parse
the same version twice and never see a half-edited document.
"""
import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.astur_bank_version import AsturBankVersion, AsturBankVersionStatus
from app.services.astur.bank import AsturBank, content_hash, parse_bank
from app.services.astur.bank_validation import BankIssue, validate_bank


@dataclass(frozen=True)
class PublishedBank:
    id: uuid.UUID
    version: int
    content_hash: str
    bank: AsturBank


_published_cache: dict[uuid.UUID, PublishedBank] = {}


def _to_published(row: AsturBankVersion) -> PublishedBank:
    cached = _published_cache.get(row.id)
    if cached is None:
        cached = PublishedBank(
            id=row.id, version=row.version, content_hash=row.content_hash, bank=parse_bank(row.document)
        )
        _published_cache[row.id] = cached
    return cached


async def latest_published(db: AsyncSession) -> PublishedBank:
    row = (
        await db.execute(
            select(AsturBankVersion)
            .where(AsturBankVersion.status == AsturBankVersionStatus.published)
            .order_by(AsturBankVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        # Version 1 is inserted by migration; reaching this is a broken DB.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No published АСТУР bank")
    return _to_published(row)


async def get_published(db: AsyncSession, version_id: uuid.UUID) -> PublishedBank:
    cached = _published_cache.get(version_id)
    if cached is not None:
        return cached
    row = await db.get(AsturBankVersion, version_id)
    if row is None or row.status != AsturBankVersionStatus.published:
        raise LookupError(f"АСТУР bank version {version_id} is not published")
    return _to_published(row)


# ── admin lifecycle ─────────────────────────────────────────────────────────


async def list_versions(db: AsyncSession) -> list[AsturBankVersion]:
    return list(
        (
            await db.execute(
                select(AsturBankVersion).order_by(
                    AsturBankVersion.version.desc().nulls_first(), AsturBankVersion.created_at.desc()
                )
            )
        ).scalars()
    )


async def get_version(db: AsyncSession, version_id: uuid.UUID, *, for_update: bool = False) -> AsturBankVersion:
    stmt = select(AsturBankVersion).where(AsturBankVersion.id == version_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank version not found")
    return row


def _require_draft(row: AsturBankVersion) -> None:
    if row.status != AsturBankVersionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A published version is immutable — create a new draft instead",
        )


async def current_draft(db: AsyncSession) -> AsturBankVersion | None:
    return (
        await db.execute(select(AsturBankVersion).where(AsturBankVersion.status == AsturBankVersionStatus.draft))
    ).scalar_one_or_none()


async def create_draft(db: AsyncSession, *, admin_id: uuid.UUID) -> AsturBankVersion:
    """Branches a new draft off the latest published version. Only one
    draft exists at a time — asking again returns the open one."""
    existing = await current_draft(db)
    if existing is not None:
        return existing
    base = await latest_published(db)
    base_row = await db.get(AsturBankVersion, base.id)
    draft = AsturBankVersion(
        status=AsturBankVersionStatus.draft,
        document=base_row.document,
        based_on_id=base.id,
        created_by=admin_id,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    return draft


async def update_draft(
    db: AsyncSession, version_id: uuid.UUID, *, document: dict, notes: str | None
) -> AsturBankVersion:
    row = await get_version(db, version_id, for_update=True)
    _require_draft(row)
    row.document = document
    row.notes = notes
    await db.commit()
    await db.refresh(row)
    return row


async def delete_draft(db: AsyncSession, version_id: uuid.UUID) -> None:
    row = await get_version(db, version_id, for_update=True)
    _require_draft(row)
    await db.delete(row)
    await db.commit()


async def _base_bank(db: AsyncSession, row: AsturBankVersion) -> AsturBank | None:
    if row.based_on_id is None:
        return None
    return (await get_published(db, row.based_on_id)).bank


async def validate_version(
    db: AsyncSession, row: AsturBankVersion, *, confirmed_item_ids: set[str] | None = None
) -> list[BankIssue]:
    base = await _base_bank(db, row) if row.status == AsturBankVersionStatus.draft else None
    return validate_bank(row.document, base=base, confirmed_item_ids=confirmed_item_ids)


async def has_changes(db: AsyncSession, row: AsturBankVersion) -> bool:
    """Whether a draft differs from the version it was branched from — an
    unchanged draft would only publish a duplicate version."""
    if row.status != AsturBankVersionStatus.draft or row.based_on_id is None:
        return True
    base = await get_published(db, row.based_on_id)
    return content_hash(row.document) != base.content_hash


async def publish(
    db: AsyncSession, version_id: uuid.UUID, *, admin_id: uuid.UUID, confirmed_item_ids: set[str]
) -> AsturBankVersion:
    row = await get_version(db, version_id, for_update=True)
    _require_draft(row)
    if not await has_changes(db, row):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The draft is identical to the version it is based on — nothing to publish",
        )
    issues = await validate_version(db, row, confirmed_item_ids=confirmed_item_ids)
    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Bank version has validation issues", "issues": [i.as_dict() for i in issues]},
        )
    next_version = (await db.execute(select(func.coalesce(func.max(AsturBankVersion.version), 0)))).scalar_one() + 1
    row.version = next_version
    row.status = AsturBankVersionStatus.published
    row.content_hash = content_hash(row.document)
    row.published_by = admin_id
    row.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def add_synonym(
    db: AsyncSession, *, admin_id: uuid.UUID, item_id: str, tier: str, locale: str, text: str
) -> AsturBankVersion:
    """Adds an accepted phrasing of an open answer to the open draft
    (branching one if needed). Only future versions change — a published
    version and the snapshots scored with it stay as they are."""
    phrase = " ".join(text.split())
    if not phrase:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty phrasing")
    draft = await create_draft(db, admin_id=admin_id)
    draft = await get_version(db, draft.id, for_update=True)
    document = copy.deepcopy(draft.document)
    item = next(
        (i for s in document["subtests"] if s["scoring_method"] == "open_text_tiers" for i in s["items"]
         if i.get("item_id") == item_id),
        None,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No open-answer item with this item_id")
    existing = {p.casefold() for t in ("score_2", "score_1") for p in item[t].get(locale, [])}
    if phrase.casefold() in existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This phrasing is already in the dictionary")
    item[tier] = {**item[tier], locale: [*item[tier].get(locale, []), phrase]}
    draft.document = document
    await db.commit()
    await db.refresh(draft)
    return draft


# ── diff ────────────────────────────────────────────────────────────────────

_ITEM_META_FIELDS = {"item_id"}


def diff_documents(before: dict, after: dict) -> list[dict]:
    """Item-level changes between two bank documents, keyed by item_id:
    `added` / `removed` / `changed` (with the changed field names) plus
    subtest-level header changes (name, instruction, timer)."""
    changes: list[dict] = []
    before_subtests = {s["key"]: s for s in before.get("subtests", [])}
    after_subtests = {s["key"]: s for s in after.get("subtests", [])}
    for key in sorted(set(before_subtests) | set(after_subtests)):
        old, new = before_subtests.get(key, {}), after_subtests.get(key, {})
        header_fields = [
            f for f in ("name", "instruction", "time_limit_sec", "scoring_method") if old.get(f) != new.get(f)
        ]
        if header_fields:
            changes.append({"kind": "subtest_changed", "subtest": key, "item_id": None, "fields": header_fields})
        old_items = {i.get("item_id"): i for i in old.get("items", [])}
        new_items = {i.get("item_id"): i for i in new.get("items", [])}
        for item_id in old_items.keys() - new_items.keys():
            changes.append({"kind": "removed", "subtest": key, "item_id": item_id, "fields": []})
        for item_id, item in new_items.items():
            previous = old_items.get(item_id)
            if previous is None:
                changes.append({"kind": "added", "subtest": key, "item_id": item_id, "fields": []})
                continue
            fields = sorted(
                f for f in (set(item) | set(previous)) - _ITEM_META_FIELDS if item.get(f) != previous.get(f)
            )
            if fields:
                changes.append({"kind": "changed", "subtest": key, "item_id": item_id, "fields": fields})
    for field in ("lability_item_limit_ms", "subjects"):
        if before.get(field) != after.get(field):
            changes.append({"kind": "bank_changed", "subtest": None, "item_id": None, "fields": [field]})
    return changes
