"""event source (demo import)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Откуда запись: NULL — создана пользователем, 'demo' — загружена из данных тестового задания
    op.add_column("events", sa.Column("source", sa.String(16)))
    op.create_index("ix_events_user_source", "events", ["user_id", "source"])


def downgrade() -> None:
    op.drop_index("ix_events_user_source", table_name="events")
    op.drop_column("events", "source")
