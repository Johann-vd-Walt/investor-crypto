"""bot_positions.quantity -> fractional (crypto)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'bot_positions', 'quantity',
        existing_type=mysql.INTEGER(),
        type_=sa.Numeric(24, 10),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'bot_positions', 'quantity',
        existing_type=sa.Numeric(24, 10),
        type_=mysql.INTEGER(),
        existing_nullable=False,
    )
