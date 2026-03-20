"""add draft_items to send_schedules.

Revision ID: 011
Revises: 010
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "send_schedules" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("send_schedules")}
    if "draft_items" not in cols:
        op.add_column(
            "send_schedules",
            sa.Column("draft_items", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("send_schedules", "draft_items")
