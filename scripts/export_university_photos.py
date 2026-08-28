"""Build the portable, slug-keyed university-photo folder.

Reads the primary UniversityImage per university, loads its bytes from the
current storage folder (addressed by the per-DB `storage_key`), and writes
`<out>/universities/<slug>.webp` — re-encoding everything to WebP so the
folder is uniform.

The result depends on this database ONLY at build time. Once produced, the
folder is addressed purely by University.slug, which any correctly-seeded DB
reproduces (curated KZ slugs are hard-coded in committed data files; jinaq
slugs are a deterministic slugify over the committed universities.json). So
the folder can be shipped to any host and served as-is — see
app/integrations/storage/university_photos.py for the read side.

Run inside the api container:
  docker-compose exec api python scripts/export_university_photos.py [--source DIR] [--out DIR]

Then hand `<out>` to whoever deploys the host (tar it up); locally, point
MEDIA_DIR at it.
"""
import argparse
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.integrations.storage.university_photos import photo_slug
from app.models.university import University
from app.models.university_image import UniversityImage
from app.services.university_photo_import_service import optimize_image


async def main(*, source: Path, out: Path) -> None:
    photos_out = out / "universities"
    photos_out.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped_missing_file = 0
    skipped_bad_image = 0
    seen_slugs: dict[str, str] = {}  # photo_slug -> University.slug (collision guard)

    async with async_session() as db:
        rows = (
            await db.execute(
                select(University.slug, UniversityImage.storage_key)
                .join(UniversityImage, UniversityImage.university_id == University.id)
                .where(UniversityImage.is_primary.is_(True))
                .where(University.slug.is_not(None))
                .order_by(University.slug)
            )
        ).all()

    for slug, storage_key in rows:
        stem = photo_slug(slug)
        if stem in seen_slugs:
            print(f"  COLLISION: '{slug}' and '{seen_slugs[stem]}' both map to {stem}.webp — skipped")
            continue

        src_file = source / storage_key
        if not src_file.is_file():
            skipped_missing_file += 1
            continue

        try:
            data, _content_type, _w, _h = optimize_image(src_file.read_bytes())
        except Exception as exc:  # noqa: BLE001 — one unreadable source must not abort the export
            print(f"  BAD IMAGE for '{slug}' ({storage_key}): {exc!r} — skipped")
            skipped_bad_image += 1
            continue

        (photos_out / f"{stem}.webp").write_bytes(data)
        seen_slugs[stem] = slug
        written += 1

    print(
        f"\nDone. Wrote {written} photos to {photos_out}\n"
        f"  skipped (source file missing): {skipped_missing_file}\n"
        f"  skipped (unreadable image):    {skipped_bad_image}\n\n"
        f"Next: tar czf media.tar.gz -C {out} universities   # hand this to the host\n"
        f"      locally: point MEDIA_DIR at {out}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=settings.STORAGE_FS_ROOT,
        help="folder the current photos live in, addressed by storage_key (default: STORAGE_FS_ROOT)",
    )
    parser.add_argument(
        "--out",
        default=settings.STORAGE_FS_ROOT,
        help=(
            "output root — writes <out>/universities/<slug>.webp (default: STORAGE_FS_ROOT, "
            "i.e. straight into the served media folder; scripts/generate_card_thumbnails.py "
            "then adds the .card.webp variants next to them)"
        ),
    )
    args = parser.parse_args()
    asyncio.run(main(source=Path(args.source), out=Path(args.out)))
