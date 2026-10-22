"""core: transactional outbox and consumer inbox

Revision ID: core_0001
Revises: 0001
Create Date: 2026-10-21 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "core_0001"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "core_outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("message_type", sa.String(length=128), nullable=False),
        sa.Column("envelope", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_outbox")),
        sa.UniqueConstraint("event_id", name=op.f("uq_core_outbox_event_id")),
    )
    op.create_index(
        "ix_core_outbox_unpublished",
        "core_outbox",
        ["id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "core_inbox",
        sa.Column("consumer", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_core_inbox")),
    )


def downgrade() -> None:
    op.drop_table("core_inbox")
    op.drop_index(
        "ix_core_outbox_unpublished",
        table_name="core_outbox",
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_table("core_outbox")
