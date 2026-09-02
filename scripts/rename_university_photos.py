"""
SNAP-6 — apply scripts/data/slug_rename_map.json to the university photo
folder: rename `<old>.webp` / `<old>.card.webp` -> `<new>.*` so photos keep
resolving after canonicalize_university_slugs.py changed the slugs.

Photos are addressed purely by `University.slug`
(app/integrations/storage/university_photos.py); the DB records nothing. So a
slug change with no matching file rename = the photo silently disappears.

If the target name already exists it is because two files were kept for the
same institution (a pass-2 EN/RU merge: `stanford-university.webp` and
`stenfordskiy-universitet.webp` were both downloaded; the new canonical slug
is the Russian one). The existing target is the correct file; the source is
now an orphan — left in place, or removed with --delete-orphans.

Idempotent: a re-run finds the old files already gone (already renamed) and
does nothing. Dry-run by default.

Run once per environment (local, then the dev/prod media host):
  python scripts/rename_university_photos.py --media-dir ../profy-media                    # dry run
  python scripts/rename_university_photos.py --media-dir ../profy-media --apply
  python scripts/rename_university_photos.py --media-dir ../profy-media --apply --delete-orphans
"""
import argparse
import json
import os
import sys

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_MAP = os.path.join(_DIR, "slug_rename_map.json")
DEFAULT_ALIAS_MAP = os.path.join(_DIR, "photo_alias_map.json")
VARIANTS = ("", ".card")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rename-map", default=DEFAULT_MAP)
    ap.add_argument("--media-dir", default=os.environ.get("MEDIA_DIR", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "profy-media")))
    ap.add_argument("--apply", action="store_true", help="actually rename (default: dry run)")
    ap.add_argument("--delete-orphans", action="store_true",
                    help="when the target already exists, delete the now-unreferenced source file")
    args = ap.parse_args()

    with open(args.rename_map, encoding="utf-8") as f:
        rename_map: dict[str, str] = json.load(f)
    if os.path.exists(DEFAULT_ALIAS_MAP):
        with open(DEFAULT_ALIAS_MAP, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                if not k.startswith("_"):
                    rename_map.setdefault(k, v)  # hand-checked orphan-photo -> current slug

    photo_dir = os.path.join(args.media_dir, "universities")
    if not os.path.isdir(photo_dir):
        sys.exit(f"no such folder: {photo_dir}")

    renamed = missing = already = orphan = orphan_deleted = 0
    orphans: list[str] = []
    for old, new in sorted(rename_map.items()):
        for v in VARIANTS:
            src = os.path.join(photo_dir, f"{old}{v}.webp")
            dst = os.path.join(photo_dir, f"{new}{v}.webp")
            if not os.path.exists(src):
                already += 1 if os.path.exists(dst) else 0
                missing += 0 if os.path.exists(dst) else 1
                continue
            if os.path.exists(dst):
                orphan += 1
                orphans.append(f"{old}{v}.webp (target {new}{v}.webp already correct)")
                if args.apply and args.delete_orphans:
                    os.remove(src)
                    orphan_deleted += 1
                continue
            if args.apply:
                os.rename(src, dst)
            renamed += 1

    print(f"{'' if args.apply else 'DRY RUN — '}rename map: {len(rename_map)} slugs, {len(VARIANTS)} variants each")
    print(f"  renamed:            {renamed}")
    print(f"  already renamed:    {already}")
    print(f"  no photo (skip):    {missing}")
    print(f"  orphan source kept: {orphan - orphan_deleted}")
    print(f"  orphan source deleted: {orphan_deleted}")
    for c in orphans:
        print(f"    {c}")


if __name__ == "__main__":
    main()
