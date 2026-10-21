"""applications: disbursement result and indexed offer expiry

Revision ID: applications_0002
Revises: applications_0001
Create Date: 2026-10-21 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "applications_0002"
down_revision: str | None = "applications_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications_applications",
        sa.Column("disbursement", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "applications_applications",
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_applications_applications_offer_expires_at"),
        "applications_applications",
        ["offer_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_applications_applications_offer_expires_at"),
        table_name="applications_applications",
    )
    op.drop_column("applications_applications", "offer_expires_at")
    op.drop_column("applications_applications", "disbursement")
