"""bot_positions.kind ('signal' | 'dca') for the accumulation sleeve

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bot_positions', sa.Column('kind', sa.String(8), nullable=False,
                                             server_default=sa.text("'signal'")))


def downgrade() -> None:
    op.drop_column('bot_positions', 'kind')
