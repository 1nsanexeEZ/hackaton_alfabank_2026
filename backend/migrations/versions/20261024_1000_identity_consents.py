"""identity: personal consents (personal data, own credit history)

Revision ID: identity_0002
Revises: process_0001
Create Date: 2026-10-24 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "identity_0002"
down_revision: str | None = "process_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_consents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_version", sa.String(length=32), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_identity_consents_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_consents")),
    )
    op.create_index(
        "ix_identity_consents_account_type",
        "identity_consents",
        ["account_id", "type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_identity_consents_account_type", table_name="identity_consents")
    op.drop_table("identity_consents")
