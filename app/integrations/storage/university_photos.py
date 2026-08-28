"""University photos are addressed by a stable key — the University.slug —
not by University.id (a per-DB random UUID). The on-disk media folder is the
single source of truth: a file `universities/<photo_slug>.webp` exists iff
that university has a photo. Nothing in the database records which photos
exist, so the folder is fully portable — drop it on any host, point any
correctly-seeded DB at it, and photos resolve by slug.

`scripts/export_university_photos.py` builds that folder; this module is the
read side (see University.image_url).
"""
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings

_PHOTO_DIR = "universities"
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9-]+")


def photo_slug(slug: str) -> str:
    """Filesystem/URL-safe form of a University.slug. Almost always identity
    (slugs are already `[a-z0-9-]`); folds the handful of rows whose slug
    still carries a stray non-ASCII char so the filename and the URL agree."""
    return _NON_SLUG_CHARS.sub("-", slug.lower()).strip("-")


@lru_cache(maxsize=1)
def slugs_with_photos() -> frozenset[str]:
    """Slugs that have a photo file in the media folder — scanned once per
    process. Empty when the folder is absent or the backend isn't `fs`
    (e.g. a future S3 deployment); callers then simply render no photo,
    never a broken image. Call `slugs_with_photos.cache_clear()` after
    changing the folder in a long-lived process."""
    if settings.STORAGE_BACKEND != "fs":
        return frozenset()
    photo_dir = Path(settings.STORAGE_FS_ROOT) / _PHOTO_DIR
    try:
        return frozenset(p.stem for p in photo_dir.glob("*.webp"))
    except OSError:
        return frozenset()


def university_photo_key(slug: str) -> str | None:
    """Relative storage key for a university's photo, or None if the folder
    has no file for this slug."""
    stem = photo_slug(slug)
    if stem not in slugs_with_photos():
        return None
    return f"{_PHOTO_DIR}/{stem}.webp"
