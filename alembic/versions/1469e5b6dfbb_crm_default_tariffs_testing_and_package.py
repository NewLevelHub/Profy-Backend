"""crm default tariffs testing and package

The price list starts with two tariffs: «Тестирование» — the test and the
report straight to the student, no calls — and «Пакет» — the two calls with
a psychologist, the test and the report after the review. «Консультация» goes:
deleted while no deal has it, archived otherwise. Runs once; after it the
owner keeps the price list in the CRM.

Revision ID: 1469e5b6dfbb
Revises: caa57fb70a62
Create Date: 2026-10-27 06:39:05.944337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1469e5b6dfbb'
down_revision: Union[str, None] = 'caa57fb70a62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TARIFFS = (
    {
        'code': 'testing', 'name': 'Тестирование', 'price': 45000, 'psychologist_review': False, 'sort': 1,
        'description': 'Тест в платформе Profile и отчёт — ученику сразу после теста, без созвонов.',
    },
    {
        'code': 'package', 'name': 'Пакет', 'price': 70000, 'psychologist_review': True, 'sort': 2,
        'description': (
            'Два созвона с психологом: знакомство (30 минут) и разбор отчёта (1 час). '
            'Тест в платформе Profile, отчёт психолог проверяет и публикует после разбора.'
        ),
    },
)


def upgrade() -> None:
    for tariff in TARIFFS:
        op.execute(
            sa.text(
                """
                INSERT INTO crm_tariffs (code, name, price, psychologist_review, description, active, sort)
                VALUES (:code, :name, :price, :psychologist_review, :description, true, :sort)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name, price = EXCLUDED.price,
                    psychologist_review = EXCLUDED.psychologist_review,
                    description = EXCLUDED.description, active = true, sort = EXCLUDED.sort
                """
            ).bindparams(**tariff)
        )
    op.execute(
        "DELETE FROM crm_tariffs WHERE code = 'consultation'"
        " AND NOT EXISTS (SELECT 1 FROM crm_deals WHERE tariff_code = 'consultation')"
    )
    op.execute("UPDATE crm_tariffs SET active = false WHERE code = 'consultation'")


def downgrade() -> None:
    # The price list is the owner's data by now; nothing to take back.
    pass
