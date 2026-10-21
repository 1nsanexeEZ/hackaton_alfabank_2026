"""notifications: feed items, news, news reads, SSE stream tickets

Revision ID: notifications_0001
Revises: products_0001
Create Date: 2026-10-22 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "notifications_0001"
down_revision: str | None = "products_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications_feed_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("recipient_type", sa.String(length=16), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("action_required", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("group_key", sa.String(length=128), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications_feed_items")),
        sa.UniqueConstraint("seq", name=op.f("uq_notifications_feed_items_seq")),
        sa.UniqueConstraint(
            "source_event_id",
            "recipient_type",
            "recipient_id",
            name=op.f("uq_notifications_feed_items_source_event_id"),
        ),
    )
    op.create_index(
        "ix_notifications_feed_items_recipient",
        "notifications_feed_items",
        ["recipient_type", "recipient_id", "seq"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_feed_items_application_id"),
        "notifications_feed_items",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_feed_items_group_key"),
        "notifications_feed_items",
        ["group_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_feed_items_organization_id"),
        "notifications_feed_items",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "notifications_news_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("okved_prefixes", postgresql.JSONB(), nullable=False),
        sa.Column("product_codes", postgresql.JSONB(), nullable=False),
        sa.Column("legal_forms", postgresql.JSONB(), nullable=False),
        sa.Column("is_general", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications_news_items")),
        sa.UniqueConstraint("slug", name=op.f("uq_notifications_news_items_slug")),
    )
    op.create_index(
        op.f("ix_notifications_news_items_published_at"),
        "notifications_news_items",
        ["published_at"],
        unique=False,
    )
    op.create_table(
        "notifications_news_reads",
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["notifications_news_items.id"],
            name=op.f("fk_notifications_news_reads_news_id_notifications_news_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("news_id", "account_id", name=op.f("pk_notifications_news_reads")),
    )
    op.create_table(
        "notifications_stream_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("roles", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications_stream_tickets")),
        sa.UniqueConstraint(
            "ticket_hash", name=op.f("uq_notifications_stream_tickets_ticket_hash")
        ),
    )
    op.create_index(
        op.f("ix_notifications_stream_tickets_expires_at"),
        "notifications_stream_tickets",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notifications_stream_tickets_expires_at"),
        table_name="notifications_stream_tickets",
    )
    op.drop_table("notifications_stream_tickets")
    op.drop_table("notifications_news_reads")
    op.drop_index(
        op.f("ix_notifications_news_items_published_at"), table_name="notifications_news_items"
    )
    op.drop_table("notifications_news_items")
    op.drop_index(
        op.f("ix_notifications_feed_items_organization_id"), table_name="notifications_feed_items"
    )
    op.drop_index(
        op.f("ix_notifications_feed_items_group_key"), table_name="notifications_feed_items"
    )
    op.drop_index(
        op.f("ix_notifications_feed_items_application_id"), table_name="notifications_feed_items"
    )
    op.drop_index("ix_notifications_feed_items_recipient", table_name="notifications_feed_items")
    op.drop_table("notifications_feed_items")
