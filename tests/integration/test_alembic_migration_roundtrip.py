"""Migration upgrade/downgrade round-trip — the whole linear chain
(`<base>` -> 0001 ... -> 0041, a single head, no branches; see
docs/rs-progress-notes.md's "Расхождение веток — РЕШЕНО" for the historical
0034/0040 numbering collision this guards against recurring), not just the
latest step.

Runs against a throwaway, freshly-created database on the same Postgres
server — never against the shared dev DB every other test in this suite
reads/writes (`alembic downgrade` drops columns/tables; doing that to the
DB other tests depend on mid-suite would be destructive). The throwaway DB
is created and dropped by this test itself via a raw asyncpg connection
(CREATE/DROP DATABASE can't run inside a SQLAlchemy transaction), and
`alembic` is invoked as the real CLI (subprocess, same as a human running
`docker-compose exec api alembic upgrade head`) with `DATABASE_URL`
overridden via the environment — `alembic/env.py` reads `settings.
DATABASE_URL`, and `Settings` is a fresh pydantic-settings instance built
by each subprocess, so the override is picked up cleanly with no monkeypatch
needed.
"""
import os
import subprocess
import uuid

import asyncpg
from sqlalchemy.engine import make_url

from app.config import settings


def _admin_dsn() -> str:
    """asyncpg DSN (not SQLAlchemy's postgresql+asyncpg://) for the
    already-existing database this project always connects to — used only
    to open the connection that issues CREATE/DROP DATABASE."""
    url = make_url(settings.DATABASE_URL)
    return f"postgresql://{url.username}:{url.password}@{url.host}:{url.port}/{url.database}"


def _throwaway_url(db_name: str) -> str:
    # str()/render_as_string() mask the password ("***") by default — this
    # URL is consumed by a subprocess, not logged, so the real password is
    # required here.
    url = make_url(settings.DATABASE_URL)
    return url.set(database=db_name).render_as_string(hide_password=False)


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        ["alembic", *args], cwd="/app", env=env, capture_output=True, text=True, timeout=120,
    )


async def test_full_migration_chain_upgrades_downgrades_and_reupgrades_cleanly() -> None:
    db_name = f"profy_migration_test_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=_admin_dsn())
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    throwaway_sqlalchemy_url = _throwaway_url(db_name)
    throwaway_asyncpg_dsn = _admin_dsn().rsplit("/", 1)[0] + f"/{db_name}"

    try:
        upgrade_1 = _run_alembic("upgrade", "head", database_url=throwaway_sqlalchemy_url)
        assert upgrade_1.returncode == 0, upgrade_1.stderr

        conn = await asyncpg.connect(dsn=throwaway_asyncpg_dsn)
        try:
            columns = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'analysis_results'"
            )
            column_names = {row["column_name"] for row in columns}
            assert {"report_version", "strength_cards", "thinking_style_notes"} <= column_names
        finally:
            await conn.close()

        downgrade = _run_alembic("downgrade", "base", database_url=throwaway_sqlalchemy_url)
        assert downgrade.returncode == 0, downgrade.stderr

        conn = await asyncpg.connect(dsn=throwaway_asyncpg_dsn)
        try:
            remaining_tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            # alembic_version itself may remain depending on driver behavior,
            # but every real app table must be gone — a clean full teardown.
            assert not {row["table_name"] for row in remaining_tables} - {"alembic_version"}
        finally:
            await conn.close()

        upgrade_2 = _run_alembic("upgrade", "head", database_url=throwaway_sqlalchemy_url)
        assert upgrade_2.returncode == 0, upgrade_2.stderr

        conn = await asyncpg.connect(dsn=throwaway_asyncpg_dsn)
        try:
            columns = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'analysis_results'"
            )
            column_names = {row["column_name"] for row in columns}
            assert {"report_version", "strength_cards", "thinking_style_notes"} <= column_names
        finally:
            await conn.close()
    finally:
        admin_conn = await asyncpg.connect(dsn=_admin_dsn())
        try:
            await admin_conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                db_name,
            )
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            await admin_conn.close()


async def test_alembic_history_is_a_single_linear_chain_with_one_head() -> None:
    """Regression guard for the exact class of bug documented in
    docs/rs-progress-notes.md: a branch that independently adds a
    same-numbered migration produces two heads, which `alembic upgrade
    head` refuses to resolve automatically. This must never merge silently."""
    result = subprocess.run(
        ["alembic", "heads"], cwd="/app", env=os.environ, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"expected exactly one alembic head, got: {heads}"
