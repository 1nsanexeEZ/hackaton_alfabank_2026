"""clients: business plans of startups

Revision ID: clients_0002
Revises: identity_0003
Create Date: 2026-10-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "clients_0002"
down_revision: str | None = "identity_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLANS = "clients_business_plans"


def upgrade() -> None:
    op.create_table(
        PLANS,
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("financial_model", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["clients_organizations.id"],
            name=op.f("fk_clients_business_plans_organization_id_clients_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_clients_business_plans")),
    )


def downgrade() -> None:
    op.drop_table(PLANS)
