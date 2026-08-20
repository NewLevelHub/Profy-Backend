"""Applies scripts/data/ovpo_registry_2026.json codes to University rows.

Two things happen here, in order:

1. Fixes a confirmed duplicate: `kazahskij-agrotehnicheskij-universitet-kazatu`
   (slug, city "Алматы") and `kazatu` (city "Астана") are the same real
   institution — КазАТУ им. Сейфуллина is in Astana, both rows share the same
   website (kazatu.edu.kz), and their 20 programs have zero name overlap
   (checked directly against the DB before writing this). The Алматы row is
   the accidental duplicate: its 14 programs are reassigned to the Астана row,
   then the duplicate University row is deleted. See
   docs/ovpo-registry-gap-analysis.md.

2. Assigns `ovpo_code` to the 43 University rows matched against the official
   registry (31 by exact name/short_name string match, 12 by hand — the
   automatic fuzzy pass produced too many false positives, e.g. it thought
   "Satbayev University" and "SDU University" were the same institution, so
   fuzzy matches were discarded rather than trusted; only checked-by-hand
   pairs are in MATCHED below). Universities not in MATCHED (military/MVD
   academies, the MSU branch, conservatory, choreography academy, etc.) are
   left without a code — they're plausibly not general-competition grant
   participants, not a matching failure.

Idempotent: safe to re-run.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/apply_ovpo_codes.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, select, update

from app.database import async_session
from app.models.program import Program
from app.models.university import University

DUPLICATE_SLUG = "kazahskij-agrotehnicheskij-universitet-kazatu"
CANONICAL_SLUG = "kazatu"

MATCHED: dict[str, str] = {
    # exact string match (31)
    "abai-kazakh-national-pedagogical-university": "007",
    "al-farabi-kazakh-national-university": "027",
    "almaty-management-university": "083",
    "astana-it-university": "522",
    "esil-university": "173",
    "kazakh-ablai-khan-university-of-international-relations-and-world-languages": "023",
    "l-n-gumilyov-eurasian-national-university": "013",
    "qairu": "111",
    "almatinskij-gumanitarno-ekonomicheskij-universitet": "154",
    "almatinskij-tehnologicheskij-universitet": "053",
    "almatinskij-universitet-energetiki-i-svyazi": "057",
    "vktu-ust-kamenogorsk": "012",
    "eagi": "047",
    "egipetskij-universitet-islamskoj-kultury-nur-mubarak": "503",
    CANONICAL_SLUG: "002",  # was mis-assigned to the Алматы duplicate; fixed by the merge below
    "kazahskij-naczionalnyj-agrarnyj-issledovatelskij-universitet": "024",
    "kazahskij-naczionalnyj-mediczinskij-universitet-im-s-d-asfendiyarova": "026",
    "kazutb": "182",
    "kazahskaya-avtomobilno-dorozhnaya-akademiya": "078",
    "kazahstansko-britanskij-tehnicheskij-universitet": "421",
    "kazahstansko-nemeczkij-universitet": "082",
    "kazahstansko-rossijskij-mediczinskij-universitet": "080",
    "kartu-karaganda": "032",
    "amu": "001",
    "medical-university-karaganda": "030",
    "mezhdunarodnyj-inzhenerno-tehnologicheskij-universitet": "049",
    "aiu": "185",
    "mezhdunarodnyj-universitet-informaczionnyh-tehnologij": "190",
    "turan-astana": "184",
    "universitet-turan": "093",
    "kazgyuu": "174",
    "satbayev-university": "029",
    "narxoz-university": "021",
    # manually verified (13 — includes yessenov-university, found while
    # double-checking the "kaspijskij-universitet" ambiguity flagged in the
    # gap-analysis doc: they're two distinct real institutions, not a dup)
    "akademiya-logistiki-i-transporta": "019",
    "cardiff-kazakhstan": "535",
    "akademiya-kajnar": "089",
    "akademiya-grazhdanskoj-aviaczii": "157",
    "kazahskaya-akademiya-sporta-i-turizma": "020",
    "kaspijskij-universitet": "079",
    "yessenov-university": "003",
    "kostanay-regional-university": "036",
    "mezhdunarodnaya-obrazovatelnaya-korporacziya": "022",
    "toraigyrov-university": "038",
    "universitet-mezhdunarodnogo-biznesa-uib": "069",
    "karsu-buketova": "031",
    "kazahskij-gosudarstvennyj-zhenskij-pedagogicheskij-universitet": "025",
}


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        # Merge duplicates
        merges = [
            (CANONICAL_SLUG, DUPLICATE_SLUG),
            ("kazgyuu", "m-narikbayev-kazguu-university")
        ]
        for canonical_slug, duplicate_slug in merges:
            result = await db.execute(
                select(University).where(University.slug.in_([duplicate_slug, canonical_slug]))
            )
            by_slug = {u.slug: u for u in result.scalars().all()}
            duplicate = by_slug.get(duplicate_slug)
            canonical = by_slug.get(canonical_slug)

            if duplicate is not None and canonical is not None:
                duplicate_progs_res = await db.execute(
                    select(Program.id, Program.name_normalized).where(Program.university_id == duplicate.id)
                )
                duplicate_progs = duplicate_progs_res.all()
                
                canonical_progs_res = await db.execute(
                    select(Program.name_normalized).where(Program.university_id == canonical.id)
                )
                canonical_progs = canonical_progs_res.scalars().all()
                
                canonical_normalized = set(canonical_progs)
                
                dup_prog_ids_to_delete = []
                prog_ids_to_reassign = []
                for pid, name_norm in duplicate_progs:
                    if name_norm in canonical_normalized:
                        dup_prog_ids_to_delete.append(pid)
                    else:
                        prog_ids_to_reassign.append(pid)
                
                print(f"[merge] {duplicate_slug} -> {canonical_slug}: processing programs (reassign: {len(prog_ids_to_reassign)}, delete duplicate: {len(dup_prog_ids_to_delete)})")
                
                if not dry_run:
                    if dup_prog_ids_to_delete:
                        await db.execute(delete(Program).where(Program.id.in_(dup_prog_ids_to_delete)))
                    if prog_ids_to_reassign:
                        await db.execute(
                            update(Program).where(Program.id.in_(prog_ids_to_reassign)).values(university_id=canonical.id)
                        )
                    await db.execute(delete(University).where(University.id == duplicate.id))
            elif duplicate is None:
                print(f"[merge] {duplicate_slug} already gone — merge previously applied")
            else:
                print(f"[merge] WARNING: canonical row {canonical_slug} not found, skipping merge")

        result = await db.execute(select(University).where(University.slug.in_(MATCHED.keys())))
        universities = {u.slug: u for u in result.scalars().all()}

        updated = 0
        unchanged = 0
        missing: list[str] = []
        for slug, code in MATCHED.items():
            uni = universities.get(slug)
            if uni is None:
                missing.append(slug)
                continue
            if uni.ovpo_code != code:
                print(f"[code] {slug}: {uni.ovpo_code!r} -> {code!r}")
                if not dry_run:
                    uni.ovpo_code = code
                updated += 1
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}ovpo_code updated: {updated}, unchanged: {unchanged}")
        if missing:
            print(f"slugs not found in DB ({len(missing)}):")
            for slug in missing:
                print(f"  - {slug}")


if __name__ == "__main__":
    asyncio.run(main())
