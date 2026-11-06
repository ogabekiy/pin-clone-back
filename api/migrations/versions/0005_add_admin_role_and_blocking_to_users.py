"""add admin role and blocking to users

Revision ID: 0005_add_admin_role_and_blocking
Revises: 0004_add_views_count_to_pins
Create Date: 2026-11-06 19:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_add_admin_role_and_blocking"
down_revision: Union[str, None] = "0004_add_views_count_to_pins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=20), server_default="user", nullable=False))
    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.alter_column("users", "google_id", nullable=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_is_blocked", "users", ["is_blocked"])


def downgrade() -> None:
    op.drop_index("ix_users_is_blocked", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.alter_column("users", "google_id", nullable=False)
    op.drop_column("users", "password_hash")
    op.drop_column("users", "is_blocked")
    op.drop_column("users", "role")

