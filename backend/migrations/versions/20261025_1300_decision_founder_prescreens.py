"""decision: prescreens of startup founders

Revision ID: decision_0003
Revises: products_0002
Create Date: 2026-10-25 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "decision_0003"
down_revision: str | None = "products_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRESCREENS = "decision_founder_prescreens"


def upgrade() -> None:
    op.create_table(
        PRESCREENS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("founder_account_id", sa.Uuid(), nullable=False),
        sa.Column("founder_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_founder_prescreens")),
    )
    op.create_index(
        "ix_decision_founder_prescreens_org", PRESCREENS, ["organization_id", "checked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_decision_founder_prescreens_org", table_name=PRESCREENS)
    op.drop_table(PRESCREENS)
