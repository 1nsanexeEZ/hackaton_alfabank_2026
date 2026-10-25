"""market: the key rate history — a rate from a date on, kept by the admin

Revision ID: market_0001
Revises: process_0002
Create Date: 2026-11-09 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "market_0001"
down_revision: str | None = "process_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "market_key_rates"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(5, 2), nullable=False),
        sa.Column("decided_on", sa.Date(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("effective_from", name=op.f("pk_market_key_rates")),
        sa.CheckConstraint(
            "value >= 0 AND value <= 100", name=op.f("ck_market_key_rates_value_range")
        ),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
