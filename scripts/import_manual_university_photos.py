"""One-time import for hand-collected photos (33 files) covering the
universities that survived two automated passes (jinaq + Wikidata) with
zero photos — see scripts/generate_missing_university_photo_review.py's
docstring for why those 33 in particular had nothing findable automatically
(mostly small/regional KZ institutions and a few foreign ones name-search
collided with unrelated entities on Wikidata). The user manually sourced and
placed these files, named `<University.name>.<ext>` (some with a
` — City, Country` suffix carried over from the earlier "list of missing
photos" message this was sourced from), in a local folder.

Reuses the exact same validate_image/optimize_image/upload pipeline as
every other photo source (app/services/university_photo_import_service.py)
so these get the same format-normalization and WebP compression as a jinaq-
or Wikidata-sourced photo would.

Matching is by exact filename (after stripping extension and any trailing
" — City, Country") against University.name, with a small hand-written
alias map for the couple of files where the saved name didn't reproduce the
DB name exactly (typo, casing, unbalanced parenthesis) — this project's
convention throughout is to never fuzzy-match identity, so an unresolved
filename is reported and skipped rather than guessed at.

Run inside the api container (photos must already be copied in, e.g.
`docker cp` to PHOTOS_DIR below):
  docker-compose exec api python scripts/import_manual_university_photos.py [--dry-run]
"""
import argparse
import asyncio
import hashlib
import os
import re
import sys
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.integrations.storage import build_storage_backend
from app.models.university import University
from app.models.university_image import UniversityImage
from app.services.university_photo_import_service import optimize_image, validate_image

PHOTOS_DIR = "/tmp/manual_photos"

# filename stem (before stripping the " — City, Country" suffix, if any) -> University.name.
# Only needed where the saved filename doesn't reproduce the DB name exactly.
FILENAME_ALIASES: dict[str, str] = {
    "Академия «Кайнар» (Q University": "Академия «Кайнар» (Q University)",
    "university of Innovation and Technology": (
        "Иностранное учебное заведение «University of Innovation and Technology» в городе Алматы"
    ),
    "Coventry University Kazakhstan": "Иностранное учебное заведение «Coventry University Kazakhstan»",
    "New York Film Academy Kazakhstan": (
        "Иностранное учебное заведение «New York Film Academy Kazakhstan» в городе Алматы"
    ),
    "Københavns Universitet, Faculty of Science — Дания, Копенгаген": (
        "Københavns Universitet (University of Copenhagen), Faculty of Science"
    ),
    "Филиал Anhalt University of Applied Sciences — Алматы": (
        "Филиал Anhalt University of Applied Sciences в городе Алматы"
    ),
    "Филиал МАИ — Байконур": (
        "Филиал МАИ (национальный исследовательский университет) в городе Байконур"
    ),
    "Филиал МГИМО МИД России — Астана": "Филиал МГИМО МИД России в городе Астана",
    "Филиал НИЯУ «МИФИ» — Алматы": "Филиал НИЯУ «МИФИ» в городе Алматы",
    "Филиал РХТУ имени Д.И. Менделеева — Тараз": (
        "Филиал РХТУ имени Д.И. Менделеева в городе Тараз"
    ),
    "Филиал Университета Гази (Gazi Üniversitesi) — Шымкент": (
        "Филиал Университета Гази (Gazi Üniversitesi) в городе Шымкент"
    ),
}


def _strip_suffix(stem: str) -> str:
    return re.sub(r"\s*—\s*[^—]+,\s*[^—,]+$", "", stem).strip()


async def main(*, dry_run: bool) -> None:
    files = sorted(os.listdir(PHOTOS_DIR))
    print(f"{len(files)} files in {PHOTOS_DIR}")

    async with async_session() as db:
        universities_by_name = {u.name: u for u in (await db.execute(select(University))).scalars().all()}

        uploaded = skipped_no_match = skipped_invalid = skipped_duplicate = 0
        unmatched: list[str] = []

        for filename in files:
            stem, _ext = os.path.splitext(filename)
            candidate_name = FILENAME_ALIASES.get(stem) or _strip_suffix(stem)
            university = universities_by_name.get(candidate_name)
            if university is None:
                unmatched.append(filename)
                skipped_no_match += 1
                continue

            with open(os.path.join(PHOTOS_DIR, filename), "rb") as f:
                data = f.read()

            validated = validate_image(data)
            if validated is None:
                print(f"[skip: invalid image] {filename}")
                skipped_invalid += 1
                continue

            data, content_type, width, height = optimize_image(data)
            checksum = hashlib.sha256(data).hexdigest()

            existing = await db.execute(
                select(UniversityImage).where(
                    UniversityImage.university_id == university.id,
                    UniversityImage.checksum_sha256 == checksum,
                )
            )
            if existing.scalar_one_or_none() is not None:
                print(f"[skip: duplicate checksum] {filename}")
                skipped_duplicate += 1
                continue

            has_images = (
                await db.execute(
                    select(UniversityImage.id).where(UniversityImage.university_id == university.id).limit(1)
                )
            ).scalar_one_or_none()
            is_primary = has_images is None

            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif"}[content_type]
            storage_key = f"universities/{university.id}/{checksum[:16]}.{ext}"

            print(f"{'[would upload]' if dry_run else '[uploading]'} {filename!r} -> {university.name!r} ({len(data)} bytes, {width}x{height})")

            if dry_run:
                uploaded += 1
                continue

            storage = build_storage_backend(settings)
            await storage.put_object(storage_key, data, content_type=content_type)
            db.add(
                UniversityImage(
                    id=uuid.uuid4(),
                    university_id=university.id,
                    storage_key=storage_key,
                    source_url=None,
                    checksum_sha256=checksum,
                    content_type=content_type,
                    width=width,
                    height=height,
                    byte_size=len(data),
                    is_primary=is_primary,
                )
            )
            uploaded += 1

        if not dry_run:
            await db.commit()

        print(
            f"\n{'DRY RUN — ' if dry_run else ''}uploaded: {uploaded}, "
            f"skipped (no match): {skipped_no_match}, skipped (invalid): {skipped_invalid}, "
            f"skipped (duplicate): {skipped_duplicate}"
        )
        if unmatched:
            print("\nUnmatched filenames (no University.name match, review FILENAME_ALIASES):")
            for f in unmatched:
                print(f"  - {f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
