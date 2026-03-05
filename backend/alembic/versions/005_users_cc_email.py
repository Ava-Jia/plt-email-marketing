"""add cc_email to users (销售注册邮箱，作为发件被CC).

Revision ID: 005
Revises: 004
Create Date: 2025-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cc_email", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "cc_email")
