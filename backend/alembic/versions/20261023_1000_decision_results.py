"""decision: results and pre-approved offers

Revision ID: decision_0001
Revises: scoring_0001
Create Date: 2026-10-23 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "decision_0001"
down_revision: str | None = "scoring_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "decision_results"
OFFERS = "decision_pre_approved_offers"


def upgrade() -> None:
    op.create_table(
        RESULTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("requested_by_command", sa.Uuid(), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("key_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("terms", postgresql.JSONB(), nullable=True),
        sa.Column("alternative_product_code", sa.String(length=32), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("client_explanation", sa.Text(), nullable=False),
        sa.Column("improvement_hints", postgresql.JSONB(), nullable=False),
        sa.Column("requested_info", postgresql.JSONB(), nullable=True),
        sa.Column("rule_trace", postgresql.JSONB(), nullable=False),
        sa.Column("limits", postgresql.JSONB(), nullable=False),
        sa.Column("decided_by_type", sa.String(length=16), nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("override_of", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_results")),
        sa.UniqueConstraint(
            "application_id", "sequence", name=op.f("uq_decision_results_application_id")
        ),
        sa.UniqueConstraint(
            "requested_by_command", name=op.f("uq_decision_results_requested_by_command")
        ),
    )
    op.create_table(
        OFFERS,
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_code", sa.String(length=32), nullable=False),
        sa.Column("max_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("rate_from", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("term_max_months", sa.Integer(), nullable=False),
        sa.Column("basis", sa.String(length=16), nullable=False),
        sa.Column("factors_summary", postgresql.JSONB(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id", "product_code", name=op.f("pk_decision_pre_approved_offers")
        ),
    )


def downgrade() -> None:
    op.drop_table(OFFERS)
    op.drop_table(RESULTS)
