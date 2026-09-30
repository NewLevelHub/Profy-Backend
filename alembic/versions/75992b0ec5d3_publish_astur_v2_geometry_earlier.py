"""Publish a new ASTUR bank version with geometry shown fourth.

Subtest numbers are stable identifiers used by the API and scoring. The new
version changes only ``presentation_order`` and clones the latest published
document, so any content edits already made by methodologists are preserved.

Revision ID: 75992b0ec5d3
Revises: 624c5e6208ee
Create Date: 2026-09-30 07:10:54.411347

"""
import hashlib
import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '75992b0ec5d3'
down_revision: Union[str, None] = '624c5e6208ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VERSION_ID = uuid.uuid5(uuid.NAMESPACE_URL, "profy:astur-bank:geometry-fourth")
_PRESENTATION_ORDER = [
    "awareness",
    "analogies",
    "lability",
    "geometric_figures",
    "classification",
    "generalization",
    "logical_schemas",
    "numeric_series",
]


def _hash(document: dict) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _versions() -> sa.TableClause:
    status = postgresql.ENUM("draft", "published", name="astur_bank_version_status_enum", create_type=False)
    return sa.table(
        "astur_bank_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("status", status),
        sa.column("document", postgresql.JSONB()),
        sa.column("content_hash", sa.String(64)),
        sa.column("based_on_id", postgresql.UUID(as_uuid=True)),
        sa.column("notes", sa.Text()),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    versions = _versions()
    connection = op.get_bind()
    if connection.execute(sa.select(versions.c.id).where(versions.c.id == _VERSION_ID)).scalar_one_or_none():
        return

    latest = connection.execute(
        sa.select(versions.c.id, versions.c.version, versions.c.document)
        .where(versions.c.status == "published")
        .order_by(versions.c.version.desc())
        .limit(1)
    ).one()
    document = json.loads(json.dumps(latest.document, ensure_ascii=False))
    document["presentation_order"] = _PRESENTATION_ORDER

    op.execute(
        versions.insert().values(
            id=_VERSION_ID,
            version=latest.version + 1,
            status="published",
            document=document,
            content_hash=_hash(document),
            based_on_id=latest.id,
            notes=(
                "Геометрические фигуры перенесены на 4-е место после лабильности; "
                "номера субтестов, задания, ключи, таймеры и scoring не изменены."
            ),
            published_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    versions = _versions()
    op.execute(versions.delete().where(versions.c.id == _VERSION_ID))
