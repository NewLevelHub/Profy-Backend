"""
One-off migration: remove the retired "it-development" slug from every
Program.direction_slugs array (see RETIRED_DIRECTION_SLUGS in
seed_akinator_content.py for why it-development itself was retired — an
accidental near-duplicate of software-engineer).

151 of 155 tagged programs already carry "software-engineer" alongside
it-development, so those just lose the redundant tag. The 4 that had
it-development as their SOLE tag ("Информатика"/"Компьютерные науки"/
"Компьютерная инженерия" at Melbourne/KTH/NTU/Bilkent) get "software-
engineer" added instead, so no program is left with an empty
direction_slugs array.

Idempotent — a re-run is a no-op once no program references it-development
anymore. Not part of the regular entrypoint.sh seed pipeline (this is a
one-time cleanup for a single retirement, not ongoing content); run by hand:
    docker-compose exec api python scripts/retag_it_development.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program

RETIRED_SLUG = "it-development"
REPLACEMENT_SLUG = "software-engineer"


async def main() -> None:
    async with async_session() as db:
        result = await db.execute(
            select(Program).where(Program.direction_slugs.contains([RETIRED_SLUG]))
        )
        programs = list(result.scalars().all())

        sole_tag_fixed = 0
        redundant_tag_dropped = 0
        for program in programs:
            slugs = [s for s in program.direction_slugs if s != RETIRED_SLUG]
            if not slugs:
                slugs = [REPLACEMENT_SLUG]
                sole_tag_fixed += 1
            else:
                redundant_tag_dropped += 1
            program.direction_slugs = slugs

        await db.commit()
        print(
            f"Retagged {len(programs)} program(s): {redundant_tag_dropped} had other tags "
            f"(just dropped {RETIRED_SLUG}), {sole_tag_fixed} had it as their sole tag "
            f"(replaced with {REPLACEMENT_SLUG})"
        )


if __name__ == "__main__":
    asyncio.run(main())
