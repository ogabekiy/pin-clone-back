"""add views_count to pins

Revision ID: 0004_add_views_count_to_pins
Revises: 0003_add_messages_table
Create Date: 2026-11-05 14:22:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_views_count_to_pins"
down_revision: Union[str, None] = "0003_add_messages_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pins", sa.Column("views_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("pins", "views_count")

