"""Applies hand-researched admission data (scripts/data/researched_kz_admission_data.json)
for KZ universities that don't participate in the state grant competition
(no ovpo_code — see scripts/apply_ovpo_codes.py) — for these, the standard
ЕНТ-classifier pipeline (apply_grant_admission_data_2026.py) has nothing to
key off, so a human researched what each one actually requires directly
from its own admissions page.

Two categories, handled differently:
  - "no_ent": ENT is genuinely irrelevant (confirmed by research, e.g.
    Nazarbayev University, a Russian-funded branch campus). Sets
    University.facilities["requires_ent"] = False (frontend then shows
    "не требуется" instead of "не установлен" for min_ent_threshold) and
    REPLACES `exams` with this university's own real entrance exams —
    there's no ЕНТ subject pair to preserve here.
  - "hybrid": ENT is still the primary/mandatory path for KZ citizens
    (confirmed by research) — the classifier-derived `exams`/
    `min_ent_threshold` already on these programs is correct and left
    untouched. Only adds what's missing: the university's OWN additional
    test/interview, language requirement, and document list, as
    supplementary facts alongside ЕНТ, not instead of it. Sets
    facilities["requires_ent"] = True for clarity.

University matching is manual (a hand-checked slug per entry below), not
fuzzy — same discipline as every other identity-matching pass in this
project; get this wrong and you attach one university's real admissions
data to a different one.

Idempotent: re-running with identical source data produces identical
`requirements`/`facilities`, so nothing changes on a second run (notes are
appended only if not already present, everything else is a plain overwrite
of the same value).

Run inside the api container:
  docker-compose exec api python scripts/apply_researched_kz_admission_data.py [--dry-run]
"""
import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.services.admin_lock import is_locked

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "researched_kz_admission_data.json")

# researched "university" label -> our slug. Hand-checked, not fuzzy-matched
# — see this script's own docstring for why.
SLUG_BY_LABEL: dict[str, str] = {
    "KIMEP University": "kimep-university",
    "Nazarbayev University": "nazarbayev-university",
    "Coventry University Kazakhstan": "coventry-university-kazakhstan",
    "De Montfort University Kazakhstan (DMUK)": "de-montfort-yuniversiti-kazahstan",
    "Geneva Business School Kazakhstan": None,  # not in our DB at all — nothing to apply
    "Казахстанско-Немецкий университет (DKU)": "kazahstansko-nemeczkij-universitet",
    "SDU University (Университет Сулеймана Демиреля)": "suleyman-demirel-university",
    "Almaty Management University (AlmaU)": "almaty-management-university",
    "Казахстанско-Британский технический университет (КБТУ)": "kazahstansko-britanskij-tehnicheskij-universitet",
    "Astana IT University (AITU)": "astana-it-university",
    "Maqsut Narikbayev University (MNU / KAZGUU)": "mnu",
    "Narxoz University (Университет Нархоз)": "narxoz-university",
    "Астанинский филиал МГУ им. М.В. Ломоносова": "msu-kz-branch",
    "Алматинский филиал НИЯУ МИФИ": "filial-niau-mifi-almaty",
    "Казахстанско-Американский свободный университет (КАСУ)": "kazakhstansko-amerikanskiy-svobodnyy-universitet",
    "Caspian University": "kaspijskij-universitet",
    "Международный университет информационных технологий (МУИТ / IITU)": "mezhdunarodnyj-universitet-informaczionnyh-tehnologij",
    "Казахско-Египетский исламский университет Нур-Мубарак": "egipetskij-universitet-islamskoj-kultury-nur-mubarak",
    "Международная образовательная корпорация (КазГАСА)": "mezhdunarodnaya-obrazovatelnaya-korporacziya",
    "Esil University": "esil-university",
    "Карагандинский университет Казпотребсоюза": "karagandinskiy-universitet-kazpotrebsoyuza",
    "Университет Мирас (Шымкент)": "universitet-miras",
    "Казахская академия спорта и туризма (KazAST)": "kazahskaya-akademiya-sporta-i-turizma",
    "Казахская национальная академия искусств им. Т. Жургенова (KazNAI)": "kazakh-national-academy-of-arts-named-after-t-zhurgenov",
}


async def main(*, dry_run: bool) -> None:
    with open(DATA_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    async with async_session() as db:
        applied = 0
        skipped_no_slug = 0
        skipped_not_found = 0

        for entry in entries:
            slug = SLUG_BY_LABEL.get(entry["university"])
            if slug is None:
                print(f"[skip] {entry['university']!r} — no confirmed slug, resolve manually")
                skipped_no_slug += 1
                continue

            uni_result = await db.execute(
                select(University).options(selectinload(University.programs)).where(University.slug == slug)
            )
            university = uni_result.scalar_one_or_none()
            if university is None:
                print(f"[skip] {entry['university']!r} -> slug {slug!r} not found in DB")
                skipped_not_found += 1
                continue

            is_no_ent = entry["category"] == "no_ent"
            if is_locked(university, "facilities"):
                print(f"Skipping facilities for {entry['university']!r} ({slug}) — admin-locked")
            else:
                facilities = dict(university.facilities or {})
                facilities["requires_ent"] = not is_no_ent
                university.facilities = facilities

            note_text = entry["notes"][0] if entry.get("notes") else None
            for program in university.programs:
                if is_locked(program, "requirements"):
                    print(f"Skipping requirements for program {program.id} ({slug}) — admin-locked")
                    continue

                requirements = dict(program.requirements or {})

                if is_no_ent:
                    requirements["exams"] = list(entry.get("exams") or [])
                    requirements.pop("min_ent_threshold", None)
                    requirements.pop("admission_scores_2026", None)

                if entry.get("min_ielts") is not None:
                    requirements["min_ielts"] = entry["min_ielts"]
                if entry.get("required_documents"):
                    requirements["source_required_documents"] = list(entry["required_documents"])
                if entry.get("portfolio_needed") is not None:
                    requirements["needs_portfolio"] = entry["portfolio_needed"]

                if note_text:
                    notes = list(requirements.get("notes") or [])
                    if note_text not in notes:
                        notes.append(note_text)
                    requirements["notes"] = notes

                program.requirements = requirements

            applied += 1
            print(f"[{'dry-run ' if dry_run else ''}applied] {entry['university']!r} ({slug}) — category={entry['category']}, programs={len(university.programs)}")

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

        print(f"\nApplied: {applied}, skipped (no slug yet): {skipped_no_slug}, skipped (slug not found): {skipped_not_found}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
