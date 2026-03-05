"""users and sales_plt_email tables.

Revision ID: 001
Revises:
Create Date: 2025-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_login"), "users", ["login"], unique=True)

    op.create_table(
        "sales_plt_email",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_id", sa.Integer(), nullable=False),
        sa.Column("plt_email", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(["sales_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sales_plt_email_id"), "sales_plt_email", ["id"], unique=False)
    op.create_index(op.f("ix_sales_plt_email_sales_id"), "sales_plt_email", ["sales_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sales_plt_email_sales_id"), table_name="sales_plt_email")
    op.drop_index(op.f("ix_sales_plt_email_id"), table_name="sales_plt_email")
    op.drop_table("sales_plt_email")
    op.drop_index(op.f("ix_users_login"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
