"""add name_i18n override column to programs

Revision ID: f4a1b8c6e2d7
Revises: e3f8a1c4d5b9
Create Date: 2026-09-08 13:30:00.000000

Follow-up to `e3f8a1c4d5b9` (universities.name_i18n). `Program.name` is the
field-of-study / specialization name shown as the card title on the
university-list page ("направления"). For Kazakhstan universities the Kazakh
form is expected on a `kk` page. Same nullable JSONB `{"kk": "..."}` overlay
and read path as `description_i18n` / `universities.name_i18n`; empty until
`scripts/apply_catalog_descriptions_kk.py apply` fills it from the
`program_names` section of `scripts/data/catalog_descriptions_kk.json`.
Changes no API response while empty (read side falls back to `name`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f4a1b8c6e2d7"
down_revision: Union[str, None] = "e3f8a1c4d5b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("programs", sa.Column("name_i18n", _JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("programs", "name_i18n")
