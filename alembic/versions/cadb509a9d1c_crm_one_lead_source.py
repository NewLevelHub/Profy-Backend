"""crm one lead source

ТЗ §3.12.1: a lead has one source — a Meta ad or a source of the list that
is not an ad — and a mark of how it was found (`attribution`). A deal that
had both keeps the ad. Sources set so far were picked by hand. The list gets
the non-ad sources the ТЗ names, if missing.

Revision ID: cadb509a9d1c
Revises: 62c6b1c8f4cd
Create Date: 2026-10-29 06:10:32.180106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cadb509a9d1c'
down_revision: Union[str, None] = '62c6b1c8f4cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAMED = ("Повторный клиент", "Рекомендация", "Органика Instagram", "Другое")


def upgrade() -> None:
    op.add_column('crm_deals', sa.Column('attribution', sa.Enum('ad', 'greeting', 'manual', name='attribution', native_enum=False, length=16), nullable=True))
    op.execute("UPDATE crm_deals SET source_id = NULL WHERE source_id IS NOT NULL AND meta_ad_id IS NOT NULL")
    op.execute("UPDATE crm_deals SET attribution = 'manual' WHERE source_id IS NOT NULL OR meta_ad_id IS NOT NULL")
    op.create_check_constraint('ck_crm_deals_one_source', 'crm_deals', 'source_id IS NULL OR meta_ad_id IS NULL')
    conn = op.get_bind()
    last = conn.execute(sa.text("SELECT coalesce(max(sort), 0) FROM crm_sources")).scalar()
    for name in NAMED:
        if conn.execute(sa.text("SELECT 1 FROM crm_sources WHERE lower(name) = lower(:n)"), {"n": name}).first() is None:
            last += 1
            conn.execute(
                sa.text("INSERT INTO crm_sources (id, name, sort) VALUES (gen_random_uuid(), :n, :s)"),
                {"n": name, "s": last},
            )


def downgrade() -> None:
    op.drop_constraint('ck_crm_deals_one_source', 'crm_deals', type_='check')
    op.drop_column('crm_deals', 'attribution')
