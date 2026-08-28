"""Downloads the Wikidata-sourced photo for each `confirmed: true` entry in
scripts/data/missing_university_photo_review.json and uploads it via the
same pipeline as apply_foreign_university_photos_from_wikidata.py — see that
script's docstring for the mechanics (external ref idempotency, Commons
redirect chain). Only 7 of the 41 checked entries were confirmed; the rest
were rejected by hand (wrong-institution name-search collisions, or a
branch campus whose parent's photo would misrepresent the actual local
building) — see missing_university_photo_review.json's `review_note` on
each.

Run inside the api container:
  docker-compose exec api python scripts/apply_missing_university_photos_from_wikidata.py [--dry-run] [--limit N]
"""
import argparse
import asyncio
import json
import os
import sys
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.integrations.storage import build_storage_backend
from app.models.university_external_ref import UniversityExternalRef
from app.services.university_photo_import_service import import_university_photos

REVIEW_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "missing_university_photo_review.json"
)
SOURCE_NAME = "wikidata"
MEDIA_BASE_URL = "https://commons.wikimedia.org"


async def main(*, dry_run: bool, limit: int | None) -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    confirmed = [e for e in review["entries"] if e["confirmed"] and e.get("image_filename")]
    if limit:
        confirmed = confirmed[:limit]
    print(f"{len(confirmed)} confirmed entries with a photo to import")

    async with async_session() as db:
        for entry in confirmed:
            existing = await db.execute(
                select(UniversityExternalRef).where(
                    UniversityExternalRef.source == SOURCE_NAME,
                    UniversityExternalRef.external_id == entry["wikidata_id"],
                )
            )
            if existing.scalar_one_or_none() is None:
                db.add(
                    UniversityExternalRef(
                        source=SOURCE_NAME,
                        external_id=entry["wikidata_id"],
                        external_name=entry["wikidata_label"],
                        university_id=entry["university_id"],
                        match_method=entry["confidence"],
                    )
                )
        await db.flush()

        institutions = [
            {
                "id": e["wikidata_id"],
                "imageUrl": "/wiki/Special:FilePath/" + urllib.parse.quote(e["image_filename"]),
            }
            for e in confirmed
        ]

        storage = build_storage_backend(settings)
        headers = {
            "User-Agent": "ProfyUniversityPhotoImport/1.0 (contact: aarhat144@gmail.com; university photo import)"
        }
        timeout = httpx.Timeout(settings.SCRAPER_REQUEST_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as http_client:
            result = await import_university_photos(
                db,
                institutions=institutions,
                source=SOURCE_NAME,
                storage=storage,
                http_client=http_client,
                media_base_url=MEDIA_BASE_URL,
                dry_run=dry_run,
            )

        if dry_run:
            await db.rollback()

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
