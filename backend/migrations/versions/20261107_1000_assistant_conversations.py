"""assistant: conversations with the smart assistant and their messages

Revision ID: assistant_0001
Revises: decision_0005
Create Date: 2026-11-07 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "assistant_0001"
down_revision: str | None = "decision_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONVERSATIONS = "assistant_conversations"
MESSAGES = "assistant_messages"


def upgrade() -> None:
    op.create_table(
        CONVERSATIONS,
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_conversations")),
    )
    op.create_index(
        op.f("ix_assistant_conversations_owner_id"), CONVERSATIONS, ["owner_id"], unique=False
    )
    op.create_table(
        MESSAGES,
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            [f"{CONVERSATIONS}.id"],
            name=op.f(f"fk_{MESSAGES}_conversation_id_{CONVERSATIONS}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_messages")),
    )
    op.create_index(
        "uq_assistant_messages_conversation_position",
        MESSAGES,
        ["conversation_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_assistant_messages_conversation_position", table_name=MESSAGES)
    op.drop_table(MESSAGES)
    op.drop_index(op.f("ix_assistant_conversations_owner_id"), table_name=CONVERSATIONS)
    op.drop_table(CONVERSATIONS)
