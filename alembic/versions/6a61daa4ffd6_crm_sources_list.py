"""crm sources list

The lead source becomes a list the owner keeps (`crm_sources`) instead of
free text. The text the deals had moves into it: each distinct value, after
trimming and ignoring case, becomes a source, so nothing is lost and the owner
archives the misspelt ones. A few common sources are added next to them.

Revision ID: 6a61daa4ffd6
Revises: 626e940ea6e6
Create Date: 2026-10-29 05:00:12.492993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6a61daa4ffd6'
down_revision: Union[str, None] = '626e940ea6e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULTS = ("Instagram", "WhatsApp", "TikTok", "Рекомендация", "Сайт", "Другое")


def upgrade() -> None:
    op.create_table('crm_sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('sort', sa.SmallInteger(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.add_column('crm_deals', sa.Column('source_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_crm_deals_source_id'), 'crm_deals', ['source_id'], unique=False)
    op.create_foreign_key('crm_deals_source_id_fkey', 'crm_deals', 'crm_sources', ['source_id'], ['id'])

    conn = op.get_bind()
    names: dict[str, str] = {}
    for name in DEFAULTS:
        names.setdefault(name.lower(), name)
    for (raw,) in conn.execute(sa.text("SELECT source FROM crm_deals WHERE source IS NOT NULL ORDER BY created_at")):
        name = " ".join(raw.split())[:120]
        if name:
            names.setdefault(name.lower(), name)
    for sort, name in enumerate(names.values()):
        conn.execute(
            sa.text("INSERT INTO crm_sources (id, name, sort) VALUES (gen_random_uuid(), :name, :sort)"),
            {"name": name, "sort": sort},
        )
    conn.execute(sa.text("""
        UPDATE crm_deals d SET source_id = s.id FROM crm_sources s
        WHERE lower(left(regexp_replace(btrim(d.source), '\\s+', ' ', 'g'), 120)) = lower(s.name)
    """))
    op.drop_column('crm_deals', 'source')


def downgrade() -> None:
    op.add_column('crm_deals', sa.Column('source', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.execute("UPDATE crm_deals d SET source = s.name FROM crm_sources s WHERE s.id = d.source_id")
    op.drop_constraint('crm_deals_source_id_fkey', 'crm_deals', type_='foreignkey')
    op.drop_index(op.f('ix_crm_deals_source_id'), table_name='crm_deals')
    op.drop_column('crm_deals', 'source_id')
    op.drop_table('crm_sources')
