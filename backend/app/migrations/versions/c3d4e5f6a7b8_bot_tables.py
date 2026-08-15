"""paper trading bot tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bot_state',
        sa.Column('id', mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('tick_seconds', mysql.INTEGER(), server_default=sa.text('60'), nullable=False),
        sa.Column('initial_cash', sa.Numeric(24, 10), nullable=False),
        sa.Column('cash', sa.Numeric(24, 10), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(24, 10), server_default=sa.text('0'), nullable=False),
        sa.Column('last_equity', sa.Numeric(24, 10), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('last_tick_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', mysql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bot_positions',
        sa.Column('id', mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column('security_id', mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column('signal_id', mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column('entry_datetime', sa.DateTime(), nullable=False),
        sa.Column('entry_price', sa.Numeric(24, 10), nullable=False),
        sa.Column('quantity', mysql.INTEGER(), nullable=False),
        sa.Column('stop_price', sa.Numeric(24, 10), nullable=True),
        sa.Column('horizon_days', mysql.SMALLINT(), server_default=sa.text('10'), nullable=False),
        sa.Column('cost_basis', sa.Numeric(24, 10), nullable=False),
        sa.Column('status', sa.String(length=8), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column('exit_datetime', sa.DateTime(), nullable=True),
        sa.Column('exit_price', sa.Numeric(24, 10), nullable=True),
        sa.Column('pnl', sa.Numeric(24, 10), nullable=True),
        sa.Column('exit_reason', sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(['security_id'], ['securities.id'], ),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bot_events',
        sa.Column('id', mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column('created_at', mysql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('ticker', sa.String(length=12), nullable=True),
        sa.Column('detail', sa.String(length=400), nullable=False),
        sa.Column('equity', sa.Numeric(24, 10), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_botevt_at', 'bot_events', ['created_at'], unique=False)
    op.create_table(
        'bot_equity',
        sa.Column('id', mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('equity', sa.Numeric(24, 10), nullable=False),
        sa.Column('cash', sa.Numeric(24, 10), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_boteq_ts', 'bot_equity', ['ts'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_boteq_ts', table_name='bot_equity')
    op.drop_table('bot_equity')
    op.drop_index('idx_botevt_at', table_name='bot_events')
    op.drop_table('bot_events')
    op.drop_table('bot_positions')
    op.drop_table('bot_state')
