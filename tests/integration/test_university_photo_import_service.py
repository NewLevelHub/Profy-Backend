"""Photo pipeline: fake StorageBackend (records calls, no real network) +
httpx.MockTransport (no real HTTP) + a real, per-test rolled-back DB session
(see tests/conftest.py) for the University/UniversityExternalRef/
UniversityImage rows.

External ids are always "test-<uuid>" strings, never plain small integers —
this dev DB has real jinaq data imported into it (real institution ids like
"1", "2", ...), and db_session's rollback-on-teardown does NOT touch rows
already committed by a real import run, so a test using a colliding id would
hit a real uq_university_external_refs_source_external_id conflict."""
import io
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage
from app.services import university_photo_import_service as svc


def _unique_id() -> str:
    return f"test-{uuid.uuid4().hex}"


class FakeStorageBackend:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        self.uploads.append((key, data, content_type))

    async def object_exists(self, key: str) -> bool:
        return any(k == key for k, _, _ in self.uploads)


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    return buf.getvalue()


def _make_http_client(routes: dict[str, tuple[int, bytes]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(str(request.url), (404, b"not found"))
        return httpx.Response(status, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _seed_university_with_ref(db_session: AsyncSession, external_id: str) -> University:
    university = University(name="Photo Test University", slug=f"photo-test-{external_id}", aliases=[], country="C", city="Y")
    db_session.add(university)
    await db_session.flush()
    db_session.add(UniversityExternalRef(source="jinaq", external_id=external_id, university_id=university.id))
    await db_session.flush()
    return university


async def test_uploads_new_photo_and_marks_it_primary(db_session: AsyncSession):
    ext_id = _unique_id()
    university = await _seed_university_with_ref(db_session, ext_id)
    storage = FakeStorageBackend()
    async with _make_http_client({"https://media.example/1.png": (200, _png_bytes())}) as http_client:
        result = await svc.import_university_photos(
            db_session,
            institutions=[{"id": ext_id, "imageUrl": "/1.png"}],
            source="jinaq",
            storage=storage,
            http_client=http_client,
            media_base_url="https://media.example",
        )

    assert result.uploaded == 1
    assert result.failed == []
    assert len(storage.uploads) == 1

    images_result = await db_session.execute(select(UniversityImage).where(UniversityImage.university_id == university.id))
    image = images_result.scalar_one()
    assert image.is_primary is True
    # The import pipeline re-encodes every source image to WebP
    # (university_photo_import_service.optimize_image) — the PNG fed in here
    # is the source format, not what ends up stored.
    assert image.content_type == "image/webp"


async def test_rerun_with_same_photo_is_idempotent_no_reupload(db_session: AsyncSession):
    ext_id = _unique_id()
    await _seed_university_with_ref(db_session, ext_id)
    storage = FakeStorageBackend()
    png = _png_bytes()

    async with _make_http_client({"https://media.example/1.png": (200, png)}) as http_client:
        first = await svc.import_university_photos(
            db_session, institutions=[{"id": ext_id, "imageUrl": "/1.png"}], source="jinaq",
            storage=storage, http_client=http_client, media_base_url="https://media.example",
        )
        second = await svc.import_university_photos(
            db_session, institutions=[{"id": ext_id, "imageUrl": "/1.png"}], source="jinaq",
            storage=storage, http_client=http_client, media_base_url="https://media.example",
        )

    assert first.uploaded == 1
    assert second.uploaded == 0
    assert second.skipped_duplicate_checksum == 1
    assert len(storage.uploads) == 1  # never re-uploaded


async def test_institution_without_ref_is_skipped_not_guessed(db_session: AsyncSession):
    # No University/ref seeded for this id at all.
    storage = FakeStorageBackend()
    async with _make_http_client({}) as http_client:
        result = await svc.import_university_photos(
            db_session, institutions=[{"id": _unique_id(), "imageUrl": "/x.png"}], source="jinaq",
            storage=storage, http_client=http_client, media_base_url="https://media.example",
        )
    assert result.skipped_no_ref == 1
    assert result.uploaded == 0
    assert storage.uploads == []


async def test_corrupt_bytes_are_skipped_without_aborting_the_batch(db_session: AsyncSession):
    ext_id_1, ext_id_2 = _unique_id(), _unique_id()
    await _seed_university_with_ref(db_session, ext_id_1)
    await _seed_university_with_ref(db_session, ext_id_2)
    storage = FakeStorageBackend()

    routes = {
        "https://media.example/bad.png": (200, b"this is not an image"),
        "https://media.example/good.png": (200, _png_bytes()),
    }
    async with _make_http_client(routes) as http_client:
        result = await svc.import_university_photos(
            db_session,
            institutions=[
                {"id": ext_id_1, "imageUrl": "/bad.png"},
                {"id": ext_id_2, "imageUrl": "/good.png"},
            ],
            source="jinaq", storage=storage, http_client=http_client, media_base_url="https://media.example",
        )

    assert result.skipped_invalid_image == 1
    assert result.uploaded == 1  # the second, valid record still went through
    assert result.failed == []


async def test_missing_image_url_is_skipped(db_session: AsyncSession):
    ext_id = _unique_id()
    await _seed_university_with_ref(db_session, ext_id)
    storage = FakeStorageBackend()
    async with _make_http_client({}) as http_client:
        result = await svc.import_university_photos(
            db_session, institutions=[{"id": ext_id, "imageUrl": None}], source="jinaq",
            storage=storage, http_client=http_client, media_base_url="https://media.example",
        )
    assert result.skipped_no_image_url == 1
    assert storage.uploads == []
