"""per-user meeting reminder lead time

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # За сколько минут до встречи присылать предупреждение (раньше было жёстко 15)
    op.add_column("users", sa.Column("meeting_lead_minutes", sa.Integer(), server_default="15", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "meeting_lead_minutes")
