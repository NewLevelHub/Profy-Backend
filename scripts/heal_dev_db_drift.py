"""Self-healing repair for a specific dev-DB drift, run automatically before
`alembic upgrade head` in docker-compose.dev.yml's api_dev command.

Context: dev's real schema fell out of sync with what its recorded
`alembic_version` claims (branch-switch / manual-stamp history — see
docs/dev-db-validity-repair.md). Concretely: `alembic_version` says
`c9f21d7e4a3b` and `d4a7e21b9f30` (which create the validity data model:
`validity_role_enum`/`sd_level_enum`/`traffic_light_enum`,
`assessment_validity`, `validity_calibration_log`,
`questions.validity_meta`/`validity_role`) already ran — so Alembic will
never revisit them — but the actual objects were never created. The next
migration, `b8911a00feb0` (remove_validity, already merged into `dev` and
must not be edited — see `scripts/migrations_fix.py`), unconditionally
deletes/drops all of that and crashes when it isn't there.

This script closes the gap *before* Alembic runs, so the unedited
`b8911a00feb0` finds exactly what it expects to remove — same effect as the
one-off manual SQL in docs/dev-db-validity-repair.md, but applied
automatically on every container start instead of by hand.

Double-guarded to be a safe no-op everywhere else:
  1. Only touches anything if the DB's current Alembic revision already has
     `d4a7e21b9f30` as an ancestor (i.e. Alembic itself considers that
     migration done) — on a fresh DB or prod's first run through this part
     of the chain, `d4a7e21b9f30` hasn't "happened" yet per alembic_version,
     so it will run for real and create these objects itself; this script
     stays out of the way entirely.
  2. Within that, each object is created only if actually missing — reruns
     (every container restart) are a fast no-op once healed.

Each phase commits its own transaction (an `ALTER TYPE ... ADD VALUE` cannot
be used in the same transaction that created it, and asyncpg's connection
cannot be reused after an explicit mid-transaction commit without ending
the transaction block cleanly), so a crash partway through can leave later
phases still to do — reruns pick up exactly where it left off, per guard 2.

Safe to delete once `b8911a00feb0` has actually run on every environment
that needs it (dev) — a fresh database or one that already passed
`b8911a00feb0` never triggers guard 1.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import engine

_REPAIR_IS_ANCESTOR_OF = "d4a7e21b9f30"  # validity_module_data_model
_REPAIR_NOT_YET_ANCESTOR_OF = "b8911a00feb0"  # remove_validity — repair is moot once this ran

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ENUM_TYPES = {
    "validity_role_enum": "CREATE TYPE validity_role_enum AS ENUM ('sd_key', 'infrequency')",
    "sd_level_enum": "CREATE TYPE sd_level_enum AS ENUM ('ok', 'social_desirability', 'high')",
    "traffic_light_enum": "CREATE TYPE traffic_light_enum AS ENUM ('green', 'yellow', 'red')",
}

_VALIDITY_CALIBRATION_LOG_DDL = """
    CREATE TABLE validity_calibration_log (
        id UUID NOT NULL,
        assessment_id UUID NOT NULL,
        sd_raw INTEGER NOT NULL,
        sd_level sd_level_enum NOT NULL,
        longstring_max INTEGER NOT NULL,
        irv DOUBLE PRECISION NOT NULL,
        infrequency_failed INTEGER NOT NULL,
        careless_flag BOOLEAN NOT NULL,
        traffic_light traffic_light_enum NOT NULL,
        age_group age_group_enum NOT NULL,
        thresholds_version INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT validity_calibration_log_pkey PRIMARY KEY (id),
        CONSTRAINT validity_calibration_log_assessment_id_fkey
            FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
    )
"""

_ASSESSMENT_VALIDITY_DDL = """
    CREATE TABLE assessment_validity (
        id UUID NOT NULL,
        assessment_id UUID NOT NULL,
        sd_raw INTEGER NOT NULL,
        sd_level sd_level_enum NOT NULL,
        longstring_max INTEGER NOT NULL,
        irv DOUBLE PRECISION NOT NULL,
        infrequency_failed INTEGER NOT NULL,
        careless_flag BOOLEAN DEFAULT false NOT NULL,
        traffic_light traffic_light_enum NOT NULL,
        details JSONB DEFAULT '{}'::jsonb NOT NULL,
        rt_ms JSONB,
        thresholds_version INTEGER NOT NULL,
        computed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT assessment_validity_pkey PRIMARY KEY (id),
        CONSTRAINT ck_assessment_validity_sd_raw_range CHECK (sd_raw >= 0 AND sd_raw <= 20),
        CONSTRAINT assessment_validity_assessment_id_fkey
            FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE,
        CONSTRAINT uq_assessment_validity_assessment_id UNIQUE (assessment_id)
    )
"""


def _needs_repair(current: str | None) -> bool:
    if current is None:
        return False
    script = ScriptDirectory.from_config(Config(os.path.join(_REPO_ROOT, "alembic.ini")))
    try:
        ancestry = {rev.revision for rev in script.iterate_revisions(current, "base")}
    except Exception:
        # Unknown/garbled current revision — never guess, let `alembic
        # upgrade head` itself report the real problem.
        return False
    # `b8911a00feb0` already ran (present in the *current* revision's own
    # ancestry, not just reachable from it) means it already removed this
    # data model as designed — recreating it now would silently undo that
    # migration forever, on every container restart.
    if _REPAIR_NOT_YET_ANCESTOR_OF in ancestry or current == _REPAIR_NOT_YET_ANCESTOR_OF:
        return False
    return _REPAIR_IS_ANCESTOR_OF in ancestry


async def _current_revision() -> str | None:
    async with engine.connect() as conn:
        try:
            async with conn.begin():
                result = await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
                return result.scalar()
        except Exception:
            # No alembic_version table yet — brand-new DB, nothing to repair.
            return None


async def _heal() -> None:
    async with engine.connect() as conn:
        async with conn.begin():
            existing_types = {
                row[0]
                for row in (
                    await conn.execute(
                        sa.text("SELECT typname FROM pg_type WHERE typname = ANY(:names)"),
                        {"names": list(_ENUM_TYPES)},
                    )
                ).all()
            }
            for name, ddl in _ENUM_TYPES.items():
                if name not in existing_types:
                    await conn.execute(sa.text(ddl))
                    print(f"[heal_dev_db_drift] created type {name}")

        # `ALTER TYPE ... ADD VALUE` must be committed before the value can be
        # used by anything else — its own transaction.
        async with conn.begin():
            has_validity_label = (
                await conn.execute(
                    sa.text(
                        "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'question_instrument_enum' AND e.enumlabel = 'validity'"
                    )
                )
            ).scalar()
            if not has_validity_label:
                await conn.execute(sa.text("ALTER TYPE question_instrument_enum ADD VALUE 'validity'"))
                print("[heal_dev_db_drift] added 'validity' to question_instrument_enum")

        async with conn.begin():
            def _inspect(sync_conn) -> dict:
                inspector = sa.inspect(sync_conn)
                return {
                    "questions_columns": {c["name"] for c in inspector.get_columns("questions")},
                    "analysis_results_columns": {c["name"] for c in inspector.get_columns("analysis_results")},
                    "has_validity_calibration_log": inspector.has_table("validity_calibration_log"),
                    "has_assessment_validity": inspector.has_table("assessment_validity"),
                }

            state = await conn.run_sync(_inspect)

            questions_columns = state["questions_columns"]
            if "validity_role" not in questions_columns:
                await conn.execute(sa.text("ALTER TABLE questions ADD COLUMN validity_role validity_role_enum"))
                print("[heal_dev_db_drift] added questions.validity_role")
            if "validity_meta" not in questions_columns:
                await conn.execute(sa.text("ALTER TABLE questions ADD COLUMN validity_meta JSONB"))
                print("[heal_dev_db_drift] added questions.validity_meta")

            analysis_results_columns = state["analysis_results_columns"]
            if "validity" not in analysis_results_columns:
                await conn.execute(sa.text("ALTER TABLE analysis_results ADD COLUMN validity JSONB"))
                print("[heal_dev_db_drift] added analysis_results.validity")

            if not state["has_validity_calibration_log"]:
                await conn.execute(sa.text(_VALIDITY_CALIBRATION_LOG_DDL))
                await conn.execute(sa.text(
                    "CREATE INDEX ix_validity_calibration_log_assessment_id "
                    "ON validity_calibration_log (assessment_id)"
                ))
                print("[heal_dev_db_drift] created table validity_calibration_log")

            if not state["has_assessment_validity"]:
                await conn.execute(sa.text(_ASSESSMENT_VALIDITY_DDL))
                await conn.execute(sa.text(
                    "CREATE UNIQUE INDEX ix_assessment_validity_assessment_id "
                    "ON assessment_validity (assessment_id)"
                ))
                print("[heal_dev_db_drift] created table assessment_validity")


async def main() -> None:
    current = await _current_revision()
    if not _needs_repair(current):
        print(f"[heal_dev_db_drift] nothing to do (current={current!r})")
        return
    await _heal()
    print(f"[heal_dev_db_drift] repair complete for revision {current!r}")


if __name__ == "__main__":
    asyncio.run(main())
