"""add subject to send_schedules.

Revision ID: 010
Revises: 009
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "send_schedules" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("send_schedules")}
    if "subject" not in cols:
        op.add_column("send_schedules", sa.Column("subject", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("send_schedules", "subject")
