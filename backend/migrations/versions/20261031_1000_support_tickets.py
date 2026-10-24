"""support: tickets of clients and their messages

Revision ID: support_0001
Revises: applications_0003
Create Date: 2026-10-31 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSequence, DropSequence

revision: str = "support_0001"
down_revision: str | None = "applications_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TICKETS = "support_tickets"
MESSAGES = "support_messages"
INDEXED = ("owner_id", "organization_id", "application_id", "assignee_id")


def upgrade() -> None:
    op.execute(CreateSequence(sa.Sequence("support_ticket_number_seq")))
    op.create_table(
        TICKETS,
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
        sa.UniqueConstraint("number", name=op.f("uq_support_tickets_number")),
    )
    for column in INDEXED:
        op.create_index(op.f(f"ix_{TICKETS}_{column}"), TICKETS, [column], unique=False)
    op.create_index(
        "ix_support_tickets_status_updated_at", TICKETS, ["status", "updated_at"], unique=False
    )
    op.create_table(
        MESSAGES,
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            [f"{TICKETS}.id"],
            name=op.f(f"fk_{MESSAGES}_ticket_id_{TICKETS}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_messages")),
    )
    op.create_index(
        "uq_support_messages_ticket_position", MESSAGES, ["ticket_id", "position"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_support_messages_ticket_position", table_name=MESSAGES)
    op.drop_table(MESSAGES)
    op.drop_index("ix_support_tickets_status_updated_at", table_name=TICKETS)
    for column in INDEXED:
        op.drop_index(op.f(f"ix_{TICKETS}_{column}"), table_name=TICKETS)
    op.drop_table(TICKETS)
    op.execute(DropSequence(sa.Sequence("support_ticket_number_seq")))
