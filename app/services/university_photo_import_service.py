"""Downloads each university's photo from the jinaq source and re-uploads it
into our own storage — see scripts/import_jinaq_university_photos.py for how
this is invoked. Must run after scripts/import_jinaq_universities.py, which
populates the UniversityExternalRef rows this looks up institutions by.

Sequential by design (like every other seed/import script in scripts/) rather
than concurrent: an AsyncSession is not safe to share across concurrent
coroutines, and correctness matters far more than shaving time off a one-time
batch job. A per-request delay (settings.SCRAPER_REQUEST_DELAY_SECONDS) is
politeness towards the source, not a performance knob.
"""
import hashlib
import io
from dataclasses import dataclass, field

import httpx
import pillow_avif  # noqa: F401 — registers AVIF decode support in Pillow on import; unused directly
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage.base import StorageBackend
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage

_MAX_IMAGE_BYTES = 15 * 1024 * 1024
_PILLOW_FORMAT_TO_CONTENT_TYPE: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "AVIF": "image/avif",
}


@dataclass
class PhotoImportResult:
    processed: int = 0
    uploaded: int = 0
    skipped_no_ref: int = 0
    skipped_no_image_url: int = 0
    skipped_duplicate_checksum: int = 0
    skipped_invalid_image: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


async def download_image(http_client: httpx.AsyncClient, url: str) -> bytes | None:
    async with http_client.stream("GET", url) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > _MAX_IMAGE_BYTES:
                return None
            chunks.append(chunk)
        return b"".join(chunks)


def validate_image(data: bytes) -> tuple[str, int | None, int | None] | None:
    """Returns (content_type, width, height) if `data` is a real, decodable
    image in an allowed format, else None. Trusts only what Pillow actually
    decoded — never the HTTP Content-Type header, which a scraped source can
    get wrong or a broken response can fake (e.g. an HTML error page served
    with a 200 and an image Content-Type)."""
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # raises on corrupt data; the object is unusable after this
    except (UnidentifiedImageError, OSError, ValueError):
        return None

    content_type = _PILLOW_FORMAT_TO_CONTENT_TYPE.get(probe.format or "")
    if content_type is None:
        return None

    try:
        # verify() leaves the image unusable — reopen to read size safely.
        with Image.open(io.BytesIO(data)) as reopened:
            width, height = reopened.size
    except (UnidentifiedImageError, OSError, ValueError):
        width, height = None, None

    return content_type, width, height


async def import_one_institution_photo(
    db: AsyncSession,
    *,
    institution: dict,
    source: str,
    storage: StorageBackend,
    http_client: httpx.AsyncClient,
    media_base_url: str,
    dry_run: bool,
) -> str:
    """Processes one jinaq institution record's photo. Returns an outcome
    tag: 'uploaded' | 'no_image_url' | 'no_ref' | 'duplicate_checksum' |
    'invalid_image' | 'failed'. Never raises — callers rely on this."""
    image_path = institution.get("imageUrl")
    if not image_path:
        return "no_image_url"

    external_id = str(institution["id"])
    ref_result = await db.execute(
        select(UniversityExternalRef).where(
            UniversityExternalRef.source == source,
            UniversityExternalRef.external_id == external_id,
        )
    )
    ref = ref_result.scalar_one_or_none()
    if ref is None:
        # The importer never does its own name matching — that trust
        # boundary lives entirely in scripts/import_jinaq_universities.py.
        return "no_ref"

    university_id = ref.university_id
    full_url = f"{media_base_url.rstrip('/')}/{image_path.lstrip('/')}"

    try:
        data = await download_image(http_client, full_url)
    except httpx.HTTPError as exc:
        return f"failed:{exc!r}"

    if data is None:
        return "failed:image too large"

    validated = validate_image(data)
    if validated is None:
        return "invalid_image"
    content_type, width, height = validated

    checksum = hashlib.sha256(data).hexdigest()

    existing_result = await db.execute(
        select(UniversityImage).where(
            UniversityImage.university_id == university_id,
            UniversityImage.checksum_sha256 == checksum,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        return "duplicate_checksum"

    if dry_run:
        return "uploaded"

    has_images_result = await db.execute(
        select(UniversityImage.id).where(UniversityImage.university_id == university_id).limit(1)
    )
    is_primary = has_images_result.scalar_one_or_none() is None

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif"}[content_type]
    storage_key = f"universities/{university_id}/{checksum[:16]}.{ext}"
    await storage.put_object(storage_key, data, content_type=content_type)

    db.add(
        UniversityImage(
            university_id=university_id,
            storage_key=storage_key,
            source_url=full_url,
            checksum_sha256=checksum,
            content_type=content_type,
            width=width,
            height=height,
            byte_size=len(data),
            is_primary=is_primary,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "duplicate_checksum"

    return "uploaded"


async def import_university_photos(
    db: AsyncSession,
    *,
    institutions: list[dict],
    source: str,
    storage: StorageBackend,
    http_client: httpx.AsyncClient,
    media_base_url: str,
    dry_run: bool = False,
) -> PhotoImportResult:
    result = PhotoImportResult()
    for institution in institutions:
        result.processed += 1
        try:
            outcome = await import_one_institution_photo(
                db,
                institution=institution,
                source=source,
                storage=storage,
                http_client=http_client,
                media_base_url=media_base_url,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 — one bad record must not abort the batch
            await db.rollback()
            result.failed.append((str(institution.get("id")), repr(exc)))
            continue

        if outcome == "uploaded":
            result.uploaded += 1
        elif outcome == "no_ref":
            result.skipped_no_ref += 1
        elif outcome == "no_image_url":
            result.skipped_no_image_url += 1
        elif outcome == "duplicate_checksum":
            result.skipped_duplicate_checksum += 1
        elif outcome == "invalid_image":
            result.skipped_invalid_image += 1
        elif outcome.startswith("failed"):
            await db.rollback()
            result.failed.append((str(institution.get("id")), outcome))

    return result
