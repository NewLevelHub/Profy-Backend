"""meta ads insights and rates

The Meta Marketing API's ads and their daily numbers, the owner's USD→₸ rate
for ad spend, the last sync, and the ad a deal came from
(app/models/meta_ads.py). Empty until the token is configured.

Revision ID: 62c6b1c8f4cd
Revises: 6a61daa4ffd6
Create Date: 2026-10-29 05:16:27.592358

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '62c6b1c8f4cd'
down_revision: Union[str, None] = '6a61daa4ffd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('meta_ads',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=400), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=True),
    sa.Column('adset_id', sa.String(length=32), nullable=True),
    sa.Column('adset_name', sa.String(length=400), nullable=True),
    sa.Column('campaign_id', sa.String(length=32), nullable=True),
    sa.Column('campaign_name', sa.String(length=400), nullable=True),
    sa.Column('creative_id', sa.String(length=32), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('meta_sync_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('full_synced_on', sa.Date(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('error_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('meta_ad_insights',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('ad_id', sa.String(length=32), nullable=False),
    sa.Column('spend', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False),
    sa.Column('impressions', sa.Integer(), server_default='0', nullable=False),
    sa.Column('reach', sa.Integer(), server_default='0', nullable=False),
    sa.Column('clicks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('link_clicks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('conversations', sa.Integer(), server_default='0', nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['ad_id'], ['meta_ads.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('day', 'ad_id')
    )
    op.create_table('meta_fx_rates',
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('rate', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('set_by', sa.UUID(), nullable=True),
    sa.Column('set_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['set_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('valid_from')
    )
    op.add_column('crm_deals', sa.Column('meta_ad_id', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_crm_deals_meta_ad_id'), 'crm_deals', ['meta_ad_id'], unique=False)
    op.create_foreign_key('crm_deals_meta_ad_id_fkey', 'crm_deals', 'meta_ads', ['meta_ad_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('crm_deals_meta_ad_id_fkey', 'crm_deals', type_='foreignkey')
    op.drop_index(op.f('ix_crm_deals_meta_ad_id'), table_name='crm_deals')
    op.drop_column('crm_deals', 'meta_ad_id')
    op.drop_table('meta_fx_rates')
    op.drop_table('meta_ad_insights')
    op.drop_table('meta_sync_state')
    op.drop_table('meta_ads')
