"""add username and pin_views

Revision ID: 0002_add_username_and_pin_views
Revises: 0001_initial_schema
Create Date: 2026-11-05 13:18:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_username_and_pin_views"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add username to users
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 2. Backfill username for existing users from email
    op.execute("UPDATE users SET username = split_part(email, '@', 1) WHERE username IS NULL;")

    # 3. Create pin_views table
    op.create_table(
        "pin_views",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pin_id", sa.BigInteger(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pin_id"], ["pins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pin_views_user_id", "pin_views", ["user_id"])
    op.create_index("ix_pin_views_pin_id", "pin_views", ["pin_id"])
    op.create_index("pin_views_user_viewed_idx", "pin_views", ["user_id", "viewed_at"])


def downgrade() -> None:
    op.drop_table("pin_views")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")

