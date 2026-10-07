"""add name_i18n override column to universities

Revision ID: e3f8a1c4d5b9
Revises: c4e7f1a9d2b6
Create Date: 2026-09-08 12:00:00.000000

Follow-up to KZ-501/504/505. `University.name` is an official institution name
kept in Russian (KZ-206 "raw catalog data"), but for Kazakhstan universities
the Kazakh official name is well-defined and expected on a `kk` page. This adds
a nullable sibling JSONB column `{"kk": "..."}` — same shape and read path as
`description_i18n` — holding only the non-`ru` name. Empty until
`scripts/apply_catalog_descriptions_kk.py apply` fills it from the
`university_names` section of `scripts/data/catalog_descriptions_kk.json`; while
empty the read side falls back to `name`, so this migration changes no API
response.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3f8a1c4d5b9"
down_revision: Union[str, None] = "c4e7f1a9d2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("universities", sa.Column("name_i18n", _JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("universities", "name_i18n")
