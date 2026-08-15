"""derivative_metrics (Binance futures positioning time series)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-14 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'derivative_metrics',
        sa.Column('security_id', mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column('metric', sa.String(length=24), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('value', sa.Numeric(precision=30, scale=10), nullable=False),
        sa.Column('ingested_at', mysql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['security_id'], ['securities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('security_id', 'metric', 'ts'),
    )


def downgrade() -> None:
    op.drop_table('derivative_metrics')
