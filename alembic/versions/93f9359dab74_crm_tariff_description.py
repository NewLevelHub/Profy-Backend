"""crm tariff description

Revision ID: 93f9359dab74
Revises: 9ea3b96a00af
Create Date: 2026-10-22 09:06:38.849695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '93f9359dab74'
down_revision: Union[str, None] = '9ea3b96a00af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crm_tariffs', sa.Column('description', sa.String(length=1000), nullable=True))
    # «Что входит» used to be hard-coded in the CRM page; now it is the owner's to edit.
    tariffs = sa.table('crm_tariffs', sa.column('code', sa.String), sa.column('description', sa.String))
    for code, text in (
        ('testing', 'Вступительный созвон, диагностика в платформе Profile, отчёт.'),
        ('consultation', 'Созвон со специалистом 60 минут без диагностики.'),
        ('package', 'Вступительный созвон, диагностика, отчёт и разбор с родителем.'),
    ):
        op.execute(tariffs.update().where(tariffs.c.code == code).values(description=text))


def downgrade() -> None:
    op.drop_column('crm_tariffs', 'description')
