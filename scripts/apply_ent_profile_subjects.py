"""
Replaces Program.requirements["exams"] for Kazakhstani programs with the
OFFICIAL ЕНТ profile-subject pair per the state classifier (Приложение 1 к
Правилам проведения ЕНТ, МНВО РК) — see university-cards-ux-fix-plan.md
§8-9. Previously this field was populated per-university from website
research (1205 of 1238 KZ programs already had *some* pair, but sourced from
each university's own site, not the government registry — see B036/B057
drift example in the research report this script is built from).

This is a REPLACE, not just a gap-fill: the point is matching the official
classifier, so an existing plausible-looking pair that happens to disagree
with the state registry is exactly the kind of error this closes, not just
the 33 previously-empty rows.

Mapping is keyed by platform profession (Direction.slug), not by
university/program — the classifier's group-of-programs is fundamentally a
subject-cluster concept, and every program on the platform already carries
exactly the profession(s) it prepares someone for. 4 professions
(prepodavatel-vuza, shkolnyy-uchitel, sekretar-deloproizvoditel,
gosudarstvennyy-sluzhaschiy) don't map to one confident classifier group —
too generic / genuinely depends on the specific subject or specialization a
given program teaches — deliberately left untouched rather than guessed.

Only Program.requirements["exams"] changes; every other key in that dict
(notes, min_ent_threshold, admission_scores_2026, etc.) is preserved as-is —
this pass is scoped to subjects only, not threshold scores (a separate,
harder problem needing a Program-to-classifier-code link this pass doesn't
build, see the plan doc).

Dry-run by default. Pass --apply to commit.
  docker exec profy-backend-api-1 python scripts/apply_ent_profile_subjects.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.program import Program
from app.models.university import University

# direction_slug -> (subject1, subject2), per Приложение 1 к Правилам
# проведения ЕНТ (adilet.zan.kz/rus/docs/V2500035915 and testcenter.kz
# supplements for the В1XX extended codes).
SUBJECT_PAIRS: dict[str, tuple[str, str]] = {
    "administrator-baz-dannyh": ("Математика", "Информатика"),
    "agronom": ("Биология", "Химия"),
    "akter": ("Творческий экзамен", "Творческий экзамен"),
    "aktuariy": ("Математика", "География"),
    "analitik-dannyh": ("Математика", "Информатика"),
    "animator-2d-3d": ("Творческий экзамен", "Творческий экзамен"),
    "arheolog": ("Всемирная история", "География"),
    "arhitektor": ("Творческий экзамен", "Творческий экзамен"),
    "arhivarius": ("Казахский/Русский язык", "Казахская/Русская литература"),
    "auditor": ("Математика", "География"),
    "aviadispetcher": ("Математика", "Физика"),
    "bibliotekar": ("Казахский/Русский язык", "Казахская/Русская литература"),
    "biolog": ("Биология", "Химия"),
    "birzhevoy-broker": ("Математика", "География"),
    "biznes-perevodchik": ("Иностранный язык", "Всемирная история"),
    "buhgalter": ("Математика", "География"),
    "burovoy-inzhener-neftegazovoe-delo": ("Математика", "Физика"),
    "diplomat": ("Всемирная история", "Иностранный язык"),
    "direktor-po-logistike": ("Математика", "География"),
    "direktor-po-marketingu": ("Математика", "География"),
    "dizayner-interera": ("Творческий экзамен", "Творческий экзамен"),
    "ekonomist-analitik": ("Математика", "География"),
    "event-menedzher": ("Математика", "География"),
    "farmatsevt": ("Биология", "Химия"),
    "finansovyy-analitik": ("Математика", "География"),
    "finansovyy-konsultant": ("Математика", "География"),
    "fotograf": ("Творческий экзамен", "Творческий экзамен"),
    "geodezist": ("Математика", "География"),
    "geolog": ("Математика", "География"),
    "gid-ekskursovod": ("География", "Иностранный язык"),
    "graficheskiy-dizayner": ("Творческий экзамен", "Творческий экзамен"),
    "himik": ("Химия", "Биология"),
    "horeograf": ("Творческий экзамен", "Творческий экзамен"),
    "hr-menedzher": ("Математика", "География"),
    "hudozhnik": ("Творческий экзамен", "Творческий экзамен"),
    "inzhener-ekolog": ("Биология", "География"),
    "inzhener-elektrik": ("Математика", "Физика"),
    "inzhener-mehanik": ("Математика", "Физика"),
    "inzhener-stroitel": ("Математика", "Физика"),
    "iskusstvoved": ("Творческий экзамен", "Творческий экзамен"),
    "issledovatel-v-oblasti-biotehnologiy": ("Биология", "Химия"),
    "kreditnyy-analitik": ("Математика", "География"),
    "landshaftnyy-dizayner": ("Творческий экзамен", "Творческий экзамен"),
    "lesnichiy": ("Биология", "География"),
    "logoped": ("Биология", "География"),
    "mashinist-lokomotiva": ("Математика", "Физика"),
    "matematik": ("Математика", "Физика"),
    "meditsinskaya-sestra-medbrat": ("Биология", "Химия"),
    "menedzher-po-prodazham": ("Математика", "География"),
    "meteorolog": ("Математика", "География"),
    "modeler": ("Творческий экзамен", "Творческий экзамен"),
    "muzykant-ispolnitel": ("Творческий экзамен", "Творческий экзамен"),
    "nalogovyy-konsultant": ("Математика", "География"),
    "pilot-grazhdanskoy-aviatsii": ("Математика", "Физика"),
    "pisatel-kopirayter": ("Творческий экзамен", "Творческий экзамен"),
    "politseyskiy": ("Всемирная история", "Основы права"),
    "pr-menedzher": ("Математика", "География"),
    "predprinimatel": ("Математика", "География"),
    "prepodavatel-iskusstva": ("Творческий экзамен", "Творческий экзамен"),
    "psiholog-issledovatel": ("Биология", "География"),
    "psiholog-konsultant": ("Биология", "География"),
    "razrabotchik-programmnogo-obespecheniya": ("Математика", "Информатика"),
    "reabilitolog-ergoterapevt": ("Биология", "Химия"),
    "rezhisser": ("Творческий экзамен", "Творческий экзамен"),
    "rieltor": ("Математика", "География"),
    "sistemnyy-administrator": ("Математика", "Информатика"),
    "sistemnyy-analitik": ("Математика", "Информатика"),
    "sotsialnyy-rabotnik": ("Биология", "География"),
    "spasatel-mchs": ("Математика", "Физика"),
    "spetsialist-po-iskusstvennomu-intellektu": ("Математика", "Информатика"),
    "spetsialist-po-kadrovomu-deloproizvodstvu": ("Математика", "География"),
    "spetsialist-po-rabote-s-molodezhyu": ("Биология", "География"),
    "spetsialist-po-standartizatsii-i-sertifikatsii": ("Математика", "Физика"),
    "spetsialist-po-tamozhennomu-delu": ("Всемирная история", "Основы права"),
    "spetsialist-po-zakupkam": ("Математика", "География"),
    "spetsialist-tehnicheskoy-podderzhki": ("Математика", "Информатика"),
    "stomatolog": ("Биология", "Химия"),
    "strahovoy-agent": ("Математика", "География"),
    "strahovoy-anderrayter": ("Математика", "География"),
    "tehnolog-pischevogo-proizvodstva": ("Биология", "Химия"),
    "trener-po-sportu": ("Творческий экзамен", "Творческий экзамен"),
    "upravlyayuschiy-fermerskim-hozyaystvom": ("Биология", "Химия"),
    "upravlyayuschiy-otelem-restoranom": ("География", "Иностранный язык"),
    "veterinar": ("Биология", "Химия"),
    "vospitatel-detskogo-sada": ("Биология", "География"),
    "vrach-obschey-praktiki": ("Биология", "Химия"),
    "yurist-advokat": ("Всемирная история", "Основы права"),
    "zhurnalist": ("Творческий экзамен", "Творческий экзамен"),
    # Deliberately NOT mapped (too generic / depends on the specific subject
    # or specialization a given program teaches, no single confident
    # classifier group): prepodavatel-vuza, shkolnyy-uchitel,
    # sekretar-deloproizvoditel, gosudarstvennyy-sluzhaschiy.
}


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        progs = (
            await db.execute(
                select(Program)
                .options(selectinload(Program.directions), selectinload(Program.university))
                .join(University, Program.university_id == University.id)
                .where(University.country == "Казахстан")
            )
        ).scalars().unique().all()

        changed = 0
        unmapped_directions: set[str] = set()

        for prog in progs:
            pair = None
            for d in prog.directions:
                if d.slug in SUBJECT_PAIRS:
                    pair = SUBJECT_PAIRS[d.slug]
                    break
                unmapped_directions.add(d.slug)
            if pair is None:
                continue

            req = dict(prog.requirements or {})
            current = req.get("exams")
            new_exams = list(pair)
            if current == new_exams:
                continue

            tag = "[updating]" if apply else "[would update]"
            print(f"{tag} {prog.university.name} | {prog.name!r}: exams {current!r} -> {new_exams!r}")
            if apply:
                req["exams"] = new_exams
                prog.requirements = req
            changed += 1

        print(f"\n{changed} of {len(progs)} KZ programs {'updated' if apply else 'would be updated'}.")
        if unmapped_directions:
            print(f"\n{len(unmapped_directions)} directions with no confident classifier mapping (left untouched):")
            for slug in sorted(unmapped_directions):
                print(f"  - {slug}")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
