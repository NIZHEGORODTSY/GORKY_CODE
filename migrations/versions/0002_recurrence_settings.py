"""recurrence, user settings, ics token

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("recurrence", sa.String(32)))
    op.add_column("users", sa.Column("voice_replies", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("users", sa.Column("digest_time", sa.Time()))
    op.add_column("users", sa.Column("last_digest_on", sa.Date()))
    op.add_column("users", sa.Column("ics_token", sa.String(64), unique=True))


def downgrade() -> None:
    op.drop_column("users", "ics_token")
    op.drop_column("users", "last_digest_on")
    op.drop_column("users", "digest_time")
    op.drop_column("users", "voice_replies")
    op.drop_column("events", "recurrence")
