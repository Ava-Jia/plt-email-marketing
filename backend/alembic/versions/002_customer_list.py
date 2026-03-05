"""customer_list table.

Revision ID: 002
Revises: 001
Create Date: 2025-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_list",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=128), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("company_traits", sa.String(length=512), nullable=True),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["sales_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customer_list_id"), "customer_list", ["id"], unique=False)
    op.create_index(op.f("ix_customer_list_sales_id"), "customer_list", ["sales_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_list_sales_id"), table_name="customer_list")
    op.drop_index(op.f("ix_customer_list_id"), table_name="customer_list")
    op.drop_table("customer_list")
