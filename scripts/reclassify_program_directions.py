"""
OFFLINE developer tool — deterministically reclassifies Program.direction_slugs
from a broad section-level tag (e.g. "akinator-medicine") to the specific leaf
specialty slug(s) it actually matches, by name/profession-keyword matching
against SPECIALTIES in seed_akinator_content.py.

NO LLM. Matching is pure string containment against curated, human-readable
keyword lists — every decision is reproducible and auditable from this file
alone.

Policy (agreed with the user 2026-07-22, see profi-program-direction-tagging
memory): precision over coverage. A program with an unambiguous single-match
gets retagged to that specific slug (dropping the section tag, so it stops
leaking into every other leaf profession's search within that section). A
program with zero or multiple candidate matches is left OUT of automated
tagging entirely (direction_slugs -> []) rather than kept at the section
level — a section-level tag makes a program match EVERY leaf profession
search in that section via the parent-fallback in
program_direction_resolver.program_direction_slugs_for, which is exactly the
"stomatology search returns nursing" bug this script exists to fix. It is
acceptable for some programs to become unmatched by any direction search;
they remain visible via other university browsing paths.

This is a REVIEW-ONLY tool by default: it never writes to the database. Run
without --apply to print a report; review it; then re-run with --apply to
write the changes for real, and update the seed scripts to match (source of
truth) as a follow-up commit.

Usage (inside Docker):
    docker-compose exec api python scripts/reclassify_program_directions.py
    docker-compose exec api python scripts/reclassify_program_directions.py --apply
"""
import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.program import Program  # noqa: E402
from scripts.seed_akinator_content import SPECIALTIES  # noqa: E402

# Russian-language curation additions on top of SPECIALTIES name/professions —
# informal degree-name synonyms actually seen in KZ university catalogs that
# don't literally appear in the specialty's own name/professions list.
# Same spirit as scripts/specialty_aliases.py (English CLI aliases); kept
# separate because these are program-name-matching keywords, not query terms.
EXTRA_KEYWORDS: dict[str, list[str]] = {
    "general-medicine": ["сестринское дело", "медико-профилактическое", "лечебное дело"],
    "dentist": ["стоматолог"],
    "pharmacist": ["фармаци", "фармацевт"],
    "civil-engineering": ["строительств", "промышленное и гражданское", "водоснабжение", "теплогазоснабжение",
                           "автомобильные дороги", "геодезия", "кадастр"],
    "mechanical-engineer": ["машиностроен", "механик", "энергетик", "электроэнергетик", "автомеханик",
                             "технологические машины"],
    "software-engineer": ["информационные системы", "программн", "вычислительная техника", "информатик",
                           "компьютерные науки"],
    "data-science": ["анализ данных", "big data", "науке о данных", "наука о данных", "больших данных",
                      "бизнес-аналитика", "бизнес аналитика", "информатик", "компьютерные науки",
                      "прикладная математика"],
    "it-infrastructure-security": ["информационная безопасность", "кибербезопасност", "kибербезопасност",
                                    "сетев", "компьютерная безопасность", "телекоммуникацион",
                                    "инфокоммуникацион", "радиотехника"],
    "management-entrepreneurship": ["менеджмент", "предпринимательств", "государственное и местное управление",
                                     "логистик", "администрировани", "управление технологиями"],
    "finance-accounting": ["финанс", "учёт и аудит", "учет и аудит", "экономик", "аудит", "налоговый"],
    "marketing": ["маркетинг", "реклам"],
    "lawyer": ["юриспруденц", "правоведени", "международное право", "международная и сравнительная политология"],
    "journalist": ["журналистик", "медиакоммуникации", "массмедиа"],
    "translator": ["переводческ", "лингвистик", "иностранн"],
    "pr-specialist": ["связи с общественностью", "pr"],
    "school-teacher": ["педагог", "учитель"],
    "kindergarten-teacher": ["дошкольн"],
    "psychologist": ["психологи"],
    "social-worker": ["социальная работа"],
    "speech-therapist": ["логопед", "дефектолог"],
    "veterinary-zootechnics": ["ветеринар", "зоотехни"],
    "agronomist": ["агрономи", "агроинженер", "почвоведение", "плодоовощеводств"],
    "ecologist": ["экологи", "природопользован", "устойчивое развитие"],
    "zoologist": ["зоологи", "биологи", "биоинженерия", "биотехнологи"],
    "architect": ["архитектур"],
    "design": ["дизайн"],
    "actor": ["актёрск", "актерск"],
    "musician": ["музык", "вокальн", "инструментальн", "музыковеден"],
    "film-director": ["режиссур"],
    "cinematographer": ["операторск", "фотограф", "продюсирование кино"],
    "makeup-artist-film": ["грим", "визаж"],
    "sports-coach": ["физическая культура", "спорт"],
    "rehabilitation-therapist": ["реабилитолог", "физиотерап"],
    "food-production-tech": ["общественного питания", "технология продукции", "продовольственных продуктов",
                              "перерабатывающих производств", "пищевых производств"],
    "hospitality-manager": ["гостиничн", "ресторанн", "туризм"],
    "fire-safety-engineer": ["техносферная безопасность", "пожарн", "бжд", "безопасность жизнедеятельности"],
    "police-officer": ["правоохранительн", "юстици"],
    "pilot": ["лётная эксплуатация", "летная эксплуатация"],
}

_DEGREE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _normalize(name: str) -> str:
    return _DEGREE_SUFFIX_RE.sub("", name).strip().lower()


def _keywords_for(spec: dict) -> list[str]:
    kws = [spec["name"].lower()] + [p.lower() for p in spec.get("professions", [])]
    kws += EXTRA_KEYWORDS.get(spec["slug"], [])
    return kws


def _contains_keyword(normalized: str, kw: str) -> bool:
    """Word-boundary-anchored match: kw must start at a word boundary in
    normalized. Plain substring containment would let e.g. "спорт" match
    inside "транспорт" — a real false positive this guards against. kw is
    often a truncated stem (e.g. "энергетик" for "энергетика"), so we only
    anchor the START of kw, not its end."""
    return re.search(r"\b" + re.escape(kw), normalized) is not None


def match_specialties(program_name: str) -> list[str]:
    """Return the sorted list of specialty slugs whose keywords appear in
    (or fully contain) the normalized program name. Searches the FULL
    taxonomy, not just the program's current section tag — some seed data
    already has the wrong section (e.g. "Журналистика" tagged under
    akinator-stage-media instead of akinator-words-communication), and
    restricting to the current section would silently inherit that error."""
    normalized = _normalize(program_name)
    matches: set[str] = set()
    for spec in SPECIALTIES:
        for kw in _keywords_for(spec):
            if _contains_keyword(normalized, kw) or (
                len(normalized) > 3 and normalized in kw
            ):
                matches.add(spec["slug"])
                break
    return sorted(matches)


async def main(apply: bool) -> None:
    async with async_session() as db:
        result = await db.execute(select(Program))
        programs = list(result.scalars().all())

    section_only = [
        p for p in programs
        if p.direction_slugs and all(s.startswith("akinator-") for s in p.direction_slugs)
    ]

    retag_single: list[tuple[Program, list[str]]] = []
    retag_multi: list[tuple[Program, list[str]]] = []
    unmatched: list[Program] = []

    for p in section_only:
        matches = match_specialties(p.name)
        if len(matches) == 1:
            retag_single.append((p, matches))
        elif len(matches) > 1:
            retag_multi.append((p, matches))
        else:
            unmatched.append(p)

    print(f"Section-only-tagged programs: {len(section_only)} / {len(programs)} total")
    print(f"  -> confident single-specialty match: {len(retag_single)}")
    print(f"  -> multi-specialty match (kept, reviewed): {len(retag_multi)}")
    print(f"  -> no match -> direction_slugs will be cleared to []: {len(unmatched)}")
    print()

    print("--- Sample of confident single-match retags (first 20) ---")
    for p, matches in retag_single[:20]:
        print(f"  {p.name!r} : {p.direction_slugs} -> {matches}")

    print()
    print("--- Multi-match cases (all, please review) ---")
    for p, matches in retag_multi:
        print(f"  {p.name!r} : {p.direction_slugs} -> {matches}")

    print()
    print("--- Unmatched -> cleared to [] (all, please review) ---")
    for p in unmatched:
        print(f"  {p.name!r} : {p.direction_slugs} -> []")

    if not apply:
        print()
        print("Dry run only — nothing written. Re-run with --apply to write these changes.")
        return

    async with async_session() as db:
        for p, matches in retag_single + retag_multi:
            db_obj = await db.get(Program, p.id)
            db_obj.direction_slugs = matches
        for p in unmatched:
            db_obj = await db.get(Program, p.id)
            db_obj.direction_slugs = []
        await db.commit()
    print(f"\nApplied: {len(retag_single) + len(retag_multi)} retagged, {len(unmatched)} cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes to the database")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
