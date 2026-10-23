"""decision: project assessments of startups

Revision ID: decision_0004
Revises: clients_0002
Create Date: 2026-10-28 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "decision_0004"
down_revision: str | None = "clients_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ASSESSMENTS = "decision_project_assessments"


def upgrade() -> None:
    op.create_table(
        ASSESSMENTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_code", sa.String(length=32), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("figures", postgresql.JSONB(), nullable=False),
        sa.Column("max_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_project_assessments")),
    )
    op.create_index(
        "ix_decision_project_assessments_org", ASSESSMENTS, ["organization_id", "checked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_decision_project_assessments_org", table_name=ASSESSMENTS)
    op.drop_table(ASSESSMENTS)
