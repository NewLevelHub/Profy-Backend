"""Build the МАК card media folder (PRO-315/311 — same pattern as
export_university_photos.py, see app/integrations/storage/university_photos.py
for the university read side).

Reads raw source images from `<MEDIA_DIR>/mac-cards-raw/` (NOT a folder
inside this git repo — no image bytes belong in a code repository; that's
the whole point of the MEDIA_DIR split. Locally: `ProfOr/profy-media/
mac-cards-raw/`. The final licensed 80-100-card deck from PRO-311 drops in
there the same way — just more files, no code change), re-encodes each to
WebP via the shared `optimize_image()` helper, and writes
`<out>/mac-cards/<stem>.webp`. The result is addressed purely by filename —
independent of both repos, servable by nginx's `/media/` location straight
off disk. `mac_cards.image_path` in the DB stores that relative key
(`mac-cards/<stem>.webp`); `build_public_url()` turns it into the URL a
client actually loads (see app/integrations/storage/urls.py). No DB
involved in this script — pure filesystem transform.

Run inside the api container:
  docker-compose exec api python scripts/export_mac_cards.py [--source DIR] [--out DIR]

Then run scripts/seed_mac_cards.py to point mac_cards.image_path at the new
files (manifest already uses the .webp names this script produces).
"""
import argparse
import os
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.config import settings
from app.services.university_photo_import_service import optimize_image

# In-container path — MEDIA_DIR is bind-mounted rw at STORAGE_FS_ROOT
# (docker-compose.yml), so this and --out below share one host folder
# (ProfOr/profy-media by default) without either living in git.
_DEFAULT_SOURCE = Path(settings.STORAGE_FS_ROOT) / "mac-cards-raw"


def main(*, source: Path, out: Path) -> None:
    cards_out = out / "mac-cards"
    cards_out.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped_bad_image = 0
    for src_file in sorted(source.glob("*.jp*g")) + sorted(source.glob("*.png")):
        try:
            data, _content_type, _w, _h = optimize_image(src_file.read_bytes())
        except Exception as exc:  # noqa: BLE001 — one bad source file must not abort the export
            print(f"  BAD IMAGE {src_file.name}: {exc!r} — skipped")
            skipped_bad_image += 1
            continue
        (cards_out / f"{src_file.stem}.webp").write_bytes(data)
        written += 1

    print(
        f"\nDone. Wrote {written} cards to {cards_out}\n"
        f"  skipped (unreadable image): {skipped_bad_image}\n\n"
        f"Next: scripts/seed_mac_cards.py to point mac_cards.image_path at these files\n"
        f"      (locally, point MEDIA_DIR at {out.parent if out.name != 'media' else out})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=Path(settings.STORAGE_FS_ROOT))
    args = parser.parse_args()
    main(source=args.source, out=args.out)
