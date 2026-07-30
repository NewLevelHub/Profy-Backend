"""
Single-pass, whole-database integrity check for every place a Direction
slug gets referenced outside the akinator content module's own asserts
(which only cover its own tables — akinator_questions.resolves_pair,
mainly). Run as the LAST step of entrypoint.sh, after every seed script,
so a dangling reference anywhere fails the deploy loudly and immediately
instead of surfacing later as a 404/500 for a real user or, worse, staying
silent forever (seed_known_profession_quizzes.py has no validation of its
own and isn't in the entrypoint pipeline at all — this is the only check
that currently covers it).

Exists because retiring "it-development" (2026-07-29) turned out to be
incomplete THREE separate times before this: the live `programs` table,
then two seed scripts with their own hardcoded slug copies
(seed_astana_universities.py, seed_almaty_universities.py — these two DO
have their own per-file asserts, which is how the first two were caught),
and finally a stale `known_profession_quizzes` row that nothing checked at
all. This script is the single place that now checks everything at once.

Non-fatal by design for `programs` (a bad tag there degrades gracefully —
the program just doesn't show up under that direction) but FATAL for
`akinator_questions.resolves_pair` and `known_profession_quizzes.leaf_slug`
(a bad reference there is either already unreachable dead code or an
actively broken user-facing endpoint).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.akinator_question import AkinatorQuestion
from app.models.direction import Direction
from app.models.known_profession_quiz import KnownProfessionQuiz
from app.models.program import Program


async def main() -> None:
    async with async_session() as db:
        known_slugs = {
            d.slug for d in (await db.execute(select(Direction))).scalars().all()
        }

        # 1. programs.direction_slugs — degrades gracefully if stale, so
        #    reported as a warning, not a hard failure.
        programs = (await db.execute(select(Program))).scalars().all()
        stale_program_slugs: set[str] = set()
        affected_programs = 0
        for program in programs:
            bad = set(program.direction_slugs or []) - known_slugs
            if bad:
                stale_program_slugs |= bad
                affected_programs += 1
        if stale_program_slugs:
            print(
                f"WARNING: {affected_programs} program(s) reference unknown "
                f"direction slug(s): {sorted(stale_program_slugs)}"
            )

        # 2. akinator_questions.resolves_pair — the live engine reads this
        #    to drive question selection and cluster resolution; a dangling
        #    slug here silently loses a resolver's whole point.
        questions = (await db.execute(select(AkinatorQuestion))).scalars().all()
        bad_questions: list[tuple[int, list[str]]] = []
        for q in questions:
            bad = sorted(set(q.resolves_pair or []) - known_slugs)
            if bad:
                bad_questions.append((q.order, bad))

        # 3. known_profession_quizzes.leaf_slug — the ONLY check covering
        #    this table at all (seed_known_profession_quizzes.py has none of
        #    its own and isn't in the entrypoint pipeline).
        quizzes = (await db.execute(select(KnownProfessionQuiz))).scalars().all()
        bad_quizzes = [q.leaf_slug for q in quizzes if q.leaf_slug not in known_slugs]

        fatal = bad_questions or bad_quizzes
        if bad_questions:
            print(f"FATAL: {len(bad_questions)} akinator_question(s) reference unknown slug(s):")
            for order, slugs in bad_questions:
                print(f"  order={order}: {slugs}")
        if bad_quizzes:
            print(f"FATAL: {len(bad_quizzes)} known_profession_quiz(zes) reference unknown slug(s): {bad_quizzes}")

        if fatal:
            print("\nContent integrity check FAILED.")
            sys.exit(1)

        print(
            f"Content integrity OK: {len(known_slugs)} directions, "
            f"{len(programs)} programs ({len(stale_program_slugs)} stale slug(s) "
            f"across {affected_programs} program(s)), {len(questions)} questions, "
            f"{len(quizzes)} known-profession quizzes — all resolves_pair/leaf_slug "
            f"references valid."
        )


if __name__ == "__main__":
    asyncio.run(main())
