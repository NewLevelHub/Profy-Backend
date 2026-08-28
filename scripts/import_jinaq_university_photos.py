"""Downloads each jinaq university's photo and re-uploads it into our own
S3-compatible storage (MinIO locally, whatever's configured via STORAGE_* in
prod) — see app/services/university_photo_import_service.py for the actual
pipeline (download -> Pillow-validate -> sha256 checksum -> upload -> record
UniversityImage row).

MUST run after scripts/import_jinaq_universities.py, which populates the
university_external_refs rows this looks institutions up by; an institution
with no ref row yet is skipped and counted, never guessed.

Idempotent: an unchanged source photo (same checksum) is a total no-op on
re-run — nothing is re-uploaded.

Requires JINAQ_MEDIA_BASE_URL to be set to the jinaq site's real domain
(imageUrl in universities.json is a relative path) before this will
successfully download anything.

Run inside the api container:
  docker-compose exec api python scripts/import_jinaq_university_photos.py [--dry-run] [--limit N]
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import httpx

from app.config import settings
from app.database import async_session
from app.integrations.storage import build_storage_backend
from app.services.university_photo_import_service import import_university_photos
from scripts.import_jinaq_universities import SOURCE_NAME, DATA_PATH


async def main(*, dry_run: bool, limit: int | None) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        institutions: list[dict] = json.load(f)
    if limit:
        institutions = institutions[:limit]

    storage = build_storage_backend(settings)
    headers = {"User-Agent": settings.SCRAPER_USER_AGENT}
    timeout = httpx.Timeout(settings.SCRAPER_REQUEST_TIMEOUT_SECONDS)

    async with async_session() as db, httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
        result = await import_university_photos(
            db,
            institutions=institutions,
            source=SOURCE_NAME,
            storage=storage,
            http_client=http_client,
            media_base_url=settings.JINAQ_MEDIA_BASE_URL,
            dry_run=dry_run,
        )

    print(
        f"Processed: {result.processed}, uploaded: {result.uploaded}, "
        f"skipped (no ref): {result.skipped_no_ref}, skipped (no image url): {result.skipped_no_image_url}, "
        f"skipped (duplicate checksum): {result.skipped_duplicate_checksum}, "
        f"skipped (invalid image): {result.skipped_invalid_image}"
    )
    if result.failed:
        print(f"Failed ({len(result.failed)}):")
        for external_id, reason in result.failed:
            print(f"  {external_id}: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
