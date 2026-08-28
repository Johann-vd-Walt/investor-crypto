"""bot live-trading (Luno) controls + position venue

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-27 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bot_state', sa.Column('mode', sa.String(length=8), server_default=sa.text("'paper'"), nullable=False))
    op.add_column('bot_state', sa.Column('dry_run', sa.Boolean(), server_default=sa.text('1'), nullable=False))
    op.add_column('bot_state', sa.Column('max_order_usd', sa.Numeric(18, 2), server_default=sa.text('20'), nullable=False))
    op.add_column('bot_state', sa.Column('daily_cap_usd', sa.Numeric(18, 2), server_default=sa.text('100'), nullable=False))
    op.add_column('bot_state', sa.Column('daily_spent_usd', sa.Numeric(18, 2), server_default=sa.text('0'), nullable=False))
    op.add_column('bot_state', sa.Column('daily_spent_date', sa.Date(), nullable=True))
    op.add_column('bot_positions', sa.Column('venue', sa.String(length=8), server_default=sa.text("'paper'"), nullable=False))
    op.add_column('bot_positions', sa.Column('luno_order_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('bot_positions', 'luno_order_id')
    op.drop_column('bot_positions', 'venue')
    op.drop_column('bot_state', 'daily_spent_date')
    op.drop_column('bot_state', 'daily_spent_usd')
    op.drop_column('bot_state', 'daily_cap_usd')
    op.drop_column('bot_state', 'max_order_usd')
    op.drop_column('bot_state', 'dry_run')
    op.drop_column('bot_state', 'mode')
