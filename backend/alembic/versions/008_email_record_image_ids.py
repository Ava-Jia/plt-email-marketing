"""add image_ids column to email_records for attached images.

Revision ID: 008
Revises: 007
Create Date: 2025-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "email_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("email_records")}
    if "image_ids" not in cols:
        op.add_column("email_records", sa.Column("image_ids", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("email_records", "image_ids")

