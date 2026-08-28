"""Generate small card-sized thumbnails for the university photo folder.

The slug-keyed export (`export_university_photos.py`) writes photos at up to
1600px wide — the right size for the university *detail* page. The results
card grid shows the same photo in a ~380x128 box, so it was shipping images
10-40x larger than they render, and decoding/compositing ~a dozen of them
per scroll tick is what makes that list stutter.

This walks the export folder and writes `<slug>.card.webp` next to each
`<slug>.webp`. nginx serves them from the same `/media/universities/`
location with no config change; the frontend asks for the `.card.webp`
variant and falls back to the full image on a 404 (see cardImageUrl in
Profy-Frontend). Re-run it after `export_university_photos.py`.

    python scripts/generate_card_thumbnails.py [--media-dir DIR] [--width 560]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

_DEFAULT_MEDIA_DIR = Path(__file__).resolve().parents[2] / "profy-media" / "universities"
_CARD_SUFFIX = ".card.webp"
_QUALITY = 72


def main(*, media_dir: Path, width: int) -> int:
    if not media_dir.is_dir():
        print(f"media dir not found: {media_dir}", file=sys.stderr)
        return 1

    sources = sorted(
        p for p in media_dir.glob("*.webp") if not p.name.endswith(_CARD_SUFFIX)
    )
    if not sources:
        print(f"no *.webp photos in {media_dir}", file=sys.stderr)
        return 1

    written = skipped_fresh = failed = 0

    for src in sources:
        dst = src.with_name(src.stem + _CARD_SUFFIX)
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            skipped_fresh += 1
            continue

        try:
            with Image.open(src) as img:
                img = img.convert("RGB")
                if img.width <= width:
                    # Already small — still re-encode at card quality so the
                    # frontend always has a variant to request (no 404 + retry).
                    out = img
                else:
                    h = round(img.height * width / img.width)
                    out = img.resize((width, h), Image.LANCZOS)
                out.save(dst, format="WEBP", quality=_QUALITY, method=6)
            written += 1
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the batch
            print(f"  FAILED {src.name}: {exc!r}")
            failed += 1

    print(
        f"\nDone. wrote {written}, up-to-date {skipped_fresh}, failed {failed}\n"
        f"variant: <slug>{_CARD_SUFFIX} in {media_dir}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-dir", type=Path, default=_DEFAULT_MEDIA_DIR)
    parser.add_argument("--width", type=int, default=560)
    args = parser.parse_args()
    raise SystemExit(main(media_dir=args.media_dir, width=args.width))
