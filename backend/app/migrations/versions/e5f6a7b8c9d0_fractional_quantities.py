"""fractional quantities for crypto (signals/paper/trades)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('signals', 'suggested_size',
                    existing_type=mysql.INTEGER(), type_=sa.Numeric(24, 10), existing_nullable=True)
    op.alter_column('paper_trades', 'quantity',
                    existing_type=mysql.INTEGER(), type_=sa.Numeric(24, 10), existing_nullable=False)
    op.alter_column('trades', 'quantity',
                    existing_type=mysql.INTEGER(), type_=sa.Numeric(24, 10), existing_nullable=False)


def downgrade() -> None:
    op.alter_column('trades', 'quantity',
                    existing_type=sa.Numeric(24, 10), type_=mysql.INTEGER(), existing_nullable=False)
    op.alter_column('paper_trades', 'quantity',
                    existing_type=sa.Numeric(24, 10), type_=mysql.INTEGER(), existing_nullable=False)
    op.alter_column('signals', 'suggested_size',
                    existing_type=sa.Numeric(24, 10), type_=mysql.INTEGER(), existing_nullable=True)
