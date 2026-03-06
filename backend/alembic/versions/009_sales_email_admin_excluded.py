"""add sales_email_admin_excluded table for cleared sales.

Revision ID: 009
Revises: 008
Create Date: 2025-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sales_email_admin_excluded" in inspector.get_table_names():
        return
    op.create_table(
        "sales_email_admin_excluded",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["sales_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sales_id"),
    )
    op.create_index("ix_sales_email_admin_excluded_sales_id", "sales_email_admin_excluded", ["sales_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sales_email_admin_excluded_sales_id", table_name="sales_email_admin_excluded")
    op.drop_table("sales_email_admin_excluded")
