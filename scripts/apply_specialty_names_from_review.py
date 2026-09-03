"""
Applies the human-reviewable specialty-name research from plan §5
(university-cards-ux-fix-plan.md) to the DB: replaces the wrong
Program.name = profession-name (the seed_92_professions_universities.py bug,
program_name = direction.name) with a real, verified academic program name
found via web research, cited with a source URL in the review JSON.

Currently covers only the 2 of 13 clusters that finished real research before
the session's agent budget ran out: cluster 0 (IT) and cluster 1
(engineering). The other 11 clusters + the separate ЕНУ/КазАТУ faculty-name
bug are NOT covered here -- still open, see university-cards-ux-fix-plan.md §5.

Entries marked "needs_manual_review": true in the review JSON are skipped --
those are cases the research agent could not confidently verify (e.g. KAIST's
exact conferred degree title, University of Tokyo's ambiguous department
sorting) and deliberately did not guess on.

One real academic program can legitimately prepare a student for several of
this platform's professions at once (e.g. one "Computer Science BSc" covers
both "Разработчик программного обеспечения" and "Аналитик данных" at the same
university) -- but the current data model creates one Program row per
(university, profession) pair, all sharing identical cost/description/
requirements, differing only in `name` and which single Direction they're
linked to (see seed_92_professions_universities.py's per-direction loop).
Renaming every one of those rows to the same real name would violate the
`uq_programs_university_name_normalized` unique index. So for a review entry
covering N professions, this script MERGES: renames the first matching row to
the real name and re-links it to all N directions, then DETACHES (not
deletes) the other N-1 rows' directions -- they become invisible to
search_programs() (which joins through Program.directions) without deleting
any row, so nothing is lost and this is fully reversible.

A Program row is matched by its (university, direction) link, not by its
current name -- it's touched as long as its name isn't already the entry's
proposed_name (i.e. it hasn't already been fixed by a previous run of this
script). This also means it correctly overrides a placeholder rename applied
by anything else (e.g. a blanket direction-name -> generic-English-field-name
pass) with the real, source-verified name -- safe to re-run.

Dry-run by default -- prints every change, writes nothing. Pass --apply to
commit. Run inside the api container (docker cp this file in first, the API
container doesn't live-mount the repo):
  docker exec profy-backend-api-1 python scripts/apply_specialty_names_from_review.py [--apply]

Expects the two review JSON files to also be docker cp'd in, at
/app/scripts/data/specialty_name_review_cluster_00.json and _01.json.
"""
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import delete, insert, select

from app.database import async_session
from app.models.direction import Direction
from app.models.program import Program, program_directions
from app.models.university import University
from app.services.admin_lock import is_locked

REVIEW_FILES = [
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_00.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_01.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_02.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_03.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_04.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_06.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_08.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_09.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_10.json"),
    os.path.join(_ROOT, "scripts", "data", "specialty_name_review_cluster_12.json"),
]


async def main() -> None:
    apply = "--apply" in sys.argv

    entries = []
    for path in REVIEW_FILES:
        if not os.path.exists(path):
            print(f"missing review file: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            entries.extend(json.load(f))

    async with async_session() as db:
        renamed = 0
        detached = 0
        skipped_manual_review = 0
        skipped_already_fixed = 0
        lookup_failures: list[str] = []

        for entry in entries:
            if entry.get("needs_manual_review"):
                skipped_manual_review += 1
                continue

            uni_slug = entry["university_slug"]
            uni = (
                await db.execute(select(University).where(University.slug == uni_slug))
            ).scalar_one_or_none()
            if uni is None:
                lookup_failures.append(f"university not found: {uni_slug!r}")
                continue

            directions = []
            for prof_name in entry["cluster_professions"]:
                d = (
                    await db.execute(select(Direction).where(Direction.name == prof_name))
                ).scalar_one_or_none()
                if d is None:
                    lookup_failures.append(f"direction not found: {prof_name!r} (uni={uni_slug})")
                    continue
                directions.append(d)
            if not directions:
                continue

            new_name = entry["proposed_name"]

            matched: list[tuple[Direction, Program]] = []
            for d in directions:
                result = await db.execute(
                    select(Program)
                    .join(Program.directions)
                    .where(
                        Program.university_id == uni.id,
                        Direction.id == d.id,
                    )
                )
                # More than one row can carry the same (university, direction)
                # link if an earlier partial/duplicate seed run left stragglers
                # (e.g. a rerun of seed_92_professions_universities.py after
                # this script already renamed the "real" survivor — the
                # dedup-by-name check in that seeder no longer matches, so it
                # creates a fresh generic-named row for the same direction).
                # ALL of them must enter `matched`, not just the first —
                # otherwise a straggler keeps its own direction link forever,
                # invisible to the merge below, and the same profession ends
                # up pointing at two different programs at once.
                for row in result.scalars().all():
                    matched.append((d, row))

            if not matched:
                skipped_already_fixed += 1
                continue

            # Dedupe by the actual Program each direction currently resolves
            # to -- once merged, every direction in this entry points to the
            # SAME survivor row, so `matched` has one (direction, program)
            # pair per direction but not necessarily one per distinct
            # program. Grouping first (instead of naively treating
            # matched[1:] as "other" rows) is what makes this idempotent:
            # a fully-merged, correctly-named survivor must be recognized as
            # "nothing left to do" rather than having its own links deleted
            # as if they belonged to a duplicate.
            programs_by_id: dict = {}
            for d, p in matched:
                programs_by_id.setdefault(p.id, p)

            if len(programs_by_id) == 1:
                only_program = next(iter(programs_by_id.values()))
                if only_program.name == new_name:
                    skipped_already_fixed += 1
                    continue
                survivor = only_program
            else:
                survivor = next(
                    (p for p in programs_by_id.values() if p.name == new_name),
                    next(iter(programs_by_id.values())),
                )
            others = [p for pid, p in programs_by_id.items() if pid != survivor.id]

            tag = "[updating]" if apply else "[would update]"
            merge_note = f" (merging {len(others)} duplicate row(s))" if others else ""
            print(f"{tag} {uni.name} | {survivor.name!r} -> {new_name!r}{merge_note}")

            if apply:
                if is_locked(survivor, "name"):
                    print(f"Skipping name for program {survivor.id} — admin-locked")
                else:
                    survivor.name = new_name
                # Plain core INSERT/DELETE on the association table instead of
                # reassigning the ORM `.directions` collection on two objects
                # in the same flush -- that silently dropped the survivor's
                # own links in practice (session-level collection-diffing
                # quirk when two Program objects' collections over the same
                # secondary table are mutated in one flush), leaving the
                # survivor with zero directions and the "other" rows
                # untouched. Explicit statements have no such ambiguity.
                direction_ids = list({d.id for d, _ in matched})
                other_program_ids = [p.id for p in others]
                try:
                    existing = {
                        row[0]
                        for row in (
                            await db.execute(
                                select(program_directions.c.direction_id).where(
                                    program_directions.c.program_id == survivor.id
                                )
                            )
                        ).all()
                    }
                    to_add = [did for did in direction_ids if did not in existing]
                    if to_add:
                        await db.execute(
                            insert(program_directions),
                            [{"program_id": survivor.id, "direction_id": did} for did in to_add],
                        )
                    if other_program_ids:
                        await db.execute(
                            delete(program_directions).where(
                                program_directions.c.program_id.in_(other_program_ids),
                                program_directions.c.direction_id.in_(direction_ids),
                            )
                        )
                    await db.flush()
                except Exception as exc:  # noqa: BLE001 - report and keep going per-row
                    await db.rollback()
                    lookup_failures.append(f"FAILED to apply {uni_slug} -> {new_name!r}: {exc}")
                    continue

            renamed += 1
            detached += len(others)

        print(
            f"\n{renamed} programs {'renamed' if apply else 'would be renamed'}, "
            f"{detached} duplicate row(s) {'detached' if apply else 'would be detached'} (not deleted)."
        )
        print(f"{skipped_manual_review} entries skipped (needs_manual_review).")
        print(f"{skipped_already_fixed} entries skipped (no row found still carrying the old profession-name).")
        if lookup_failures:
            print(f"\n{len(lookup_failures)} issues:")
            for msg in lookup_failures[:50]:
                print(f"  - {msg}")

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
