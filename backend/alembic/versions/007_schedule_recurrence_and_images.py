"""add recurrence_type, day_of_month, image_ids to send_schedules.

Revision ID: 007
Revises: 006
Create Date: 2025-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "send_schedules" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("send_schedules")}
    if "recurrence_type" not in cols:
        op.add_column("send_schedules", sa.Column("recurrence_type", sa.String(length=10), nullable=False, server_default="week"))
    if "day_of_month" not in cols:
        op.add_column("send_schedules", sa.Column("day_of_month", sa.Integer(), nullable=True))
    if "image_ids" not in cols:
        op.add_column("send_schedules", sa.Column("image_ids", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("send_schedules", "image_ids")
    op.drop_column("send_schedules", "day_of_month")
    op.drop_column("send_schedules", "recurrence_type")
