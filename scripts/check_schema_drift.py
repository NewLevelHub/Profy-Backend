"""Fail on model ↔ migration drift that isn't on the known list (PRO-429, CI).

Same comparison as `alembic check` — SQLAlchemy models vs. a database that
was just brought to `alembic upgrade head` — except that differences already
recorded in alembic/known_schema_drift.txt are tolerated. `alembic check`
alone can't be a CI gate here: dev's head already carries drift that predates
the check (a dropped model whose table was never dropped, indexes that exist
only in migrations, ...), and it would fail every PR until that is resolved.

So: a *new* difference fails — you changed a model without a migration (run
`alembic revision --autogenerate`), or a migration without the model. A known
difference that disappeared also fails, so the list only ever shrinks: delete
its line.

Needs DATABASE_URL pointing at a database already at `alembic upgrade head`.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402

KNOWN_DRIFT_FILE = ROOT / "alembic" / "known_schema_drift.txt"


def _name_of(obj) -> str:
    table = getattr(obj, "table", None)
    name = getattr(obj, "name", None)
    if name is None and hasattr(obj, "columns"):
        name = "(" + ",".join(c.name for c in obj.columns) + ")"
    if table is not None and table is not obj:
        return f"{table.name}.{name}"
    return str(name)


def describe(diff: tuple) -> str:
    """Stable one-line key for one autogenerate difference."""
    op = diff[0]
    if op in ("add_column", "remove_column"):
        _op, _schema, table, column = diff
        return f"{op} {table}.{column.name}"
    if op.startswith("modify_"):
        _op, _schema, table, column = diff[:4]
        return f"{op} {table}.{column}"
    return f"{op} {_name_of(diff[1])}"


async def detect() -> set[str]:
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as connection:
            diffs = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
    finally:
        await engine.dispose()
    found = set()
    for diff in diffs:
        # modify_* differences come grouped per column as a list of tuples.
        for single in diff if isinstance(diff, list) else [diff]:
            found.add(describe(single))
    return found


def load_known() -> set[str]:
    lines = KNOWN_DRIFT_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def main() -> int:
    found, known = asyncio.run(detect()), load_known()
    new, gone = sorted(found - known), sorted(known - found)
    for key in new:
        print(f"✗ новое расхождение моделей и миграций: {key}")
    if new:
        print(
            "  Модель поменяли без миграции (или наоборот). Создайте миграцию: "
            "`alembic revision --autogenerate -m ...` и проверьте её глазами."
        )
    for key in gone:
        print(f"✗ расхождение исправлено, удалите строку из {KNOWN_DRIFT_FILE.name}: {key}")
    if new or gone:
        return 1
    print(f"OK: новых расхождений нет (известных: {len(known)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
