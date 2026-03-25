"""add fixed_text to email_records (邮件固定文本摘要).

Revision ID: 014
Revises: 013
Create Date: 2026-03-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "email_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("email_records")}
    if "fixed_text" not in cols:
        op.add_column("email_records", sa.Column("fixed_text", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "email_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("email_records")}
    if "fixed_text" in cols:
        op.drop_column("email_records", "fixed_text")

