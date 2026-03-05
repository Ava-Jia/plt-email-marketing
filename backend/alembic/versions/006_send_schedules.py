"""add send_schedules table for recurring send (module F).

Revision ID: 006
Revises: 005
Create Date: 2025-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "send_schedules" in inspector.get_table_names():
        return  # 表已存在（例如由 create_all 创建），仅标记迁移已执行
    op.create_table(
        "send_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sales_id", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("time", sa.String(length=5), nullable=False),
        sa.Column("repeat_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["sales_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["email_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_send_schedules_sales_id"), "send_schedules", ["sales_id"], unique=False)
    op.create_index(op.f("ix_send_schedules_template_id"), "send_schedules", ["template_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_send_schedules_template_id"), table_name="send_schedules")
    op.drop_index(op.f("ix_send_schedules_sales_id"), table_name="send_schedules")
    op.drop_table("send_schedules")
