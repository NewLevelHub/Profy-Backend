"""
Marks universities.uniranks_note = "Н/Р" for universities that were checked
against UNIRANKS® 2027's Kazakhstan ranking (https://www.uniranks.com/ranking/ru/казахстан,
96 confirmed universities total, no entries beyond that) and confirmed absent
from it. Complements apply_uniranks_kz_2027.py, which fills in the ones that
were found.

Run inside the api container:
  docker exec profi-backend-api-1 python scripts/apply_uniranks_not_ranked.py [--dry-run]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from app.services.admin_lock import is_locked

NOT_RANKED_SLUGS = [
    "almaty-management-university",
    "astana-it-university",
    "cardiff-kazakhstan",
    "esil-university",
    "m-narikbayev-kazguu-university",
    "qairu",
    "akademiya-fizicheskoj-kultury",
    "almatinskij-gumanitarno-ekonomicheskij-universitet",
    "almatinskij-tehnologicheskij-universitet",
    "almatinskij-universitet-energetiki-i-svyazi",
    "de-montfort-yuniversiti-kazahstan",
    "academy-of-choreography",
    "kazahskaya-naczionalnaya-konservatoriya-im-kurmangazy",
    "kazatu",
    "kazahskij-agrotehnicheskij-universitet-kazatu",
    "kaznui",
    "kazahskaya-avtomobilno-dorozhnaya-akademiya",
    "msu-kz-branch",
    "mezhdunarodnyj-inzhenerno-tehnologicheskij-universitet",
    "aiu",
    "kazgyuu",
    "universitet-mezhdunarodnogo-biznesa-uib",
    "karsu-buketova",
    "medical-university-karaganda",
    "mvd-academy-karaganda",
    "kostanay-regional-university",
    "yessenov-university",
    "voenny-institut-sil-vozdushnoy-oborony",
    "vktu-ust-kamenogorsk",
]


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        updated = 0
        unchanged = 0
        missing: list[str] = []

        for slug in NOT_RANKED_SLUGS:
            result = await db.execute(select(University).where(University.slug == slug))
            university = result.scalar_one_or_none()
            if university is None:
                missing.append(slug)
                continue

            if university.uniranks_note != "Н/Р":
                if is_locked(university, "uniranks_note"):
                    print(f"Skipping uniranks_note for {slug} — admin-locked")
                    unchanged += 1
                    continue
                updated += 1
                if dry_run:
                    print(f"[would update] {slug} -> uniranks_note='Н/Р'")
                else:
                    university.uniranks_note = "Н/Р"
            else:
                unchanged += 1

        if not dry_run:
            await db.commit()

        print(f"\n{'DRY RUN — ' if dry_run else ''}universities updated: {updated}, unchanged: {unchanged}, missing: {len(missing)}")
        if missing:
            print("Missing slugs (not found in DB):")
            for m in missing:
                print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
