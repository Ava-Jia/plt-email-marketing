"""add fixed_text to email_templates (AI 后与图片前的固定正文).

Revision ID: 013
Revises: 012
Create Date: 2026-03-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "email_templates" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("email_templates")}
    if "fixed_text" not in cols:
        op.add_column("email_templates", sa.Column("fixed_text", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "email_templates" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("email_templates")}
    if "fixed_text" in cols:
        op.drop_column("email_templates", "fixed_text")
